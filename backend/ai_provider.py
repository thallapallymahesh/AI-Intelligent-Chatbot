"""Configurable chat and embedding providers for local and hosted deployments."""

import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import ollama

logger = logging.getLogger(__name__)

AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
AI_API_BASE_URL = os.getenv("AI_API_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_CHAT_MODEL = os.getenv("AI_CHAT_MODEL", "llama3.2")
AI_EMBEDDING_MODEL = os.getenv("AI_EMBEDDING_MODEL", "nomic-embed-text")
GEMINI_API_BASE_URL = os.getenv(
    "AI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
).rstrip("/")


class ProviderConfigurationError(RuntimeError):
    pass


def _check_provider():
    if AI_PROVIDER not in {"ollama", "openai", "gemini"}:
        raise ProviderConfigurationError("AI_PROVIDER must be 'ollama', 'openai', or 'gemini'.")
    if AI_PROVIDER in {"openai", "gemini"} and not AI_API_KEY:
        raise ProviderConfigurationError(f"AI_API_KEY is required when AI_PROVIDER={AI_PROVIDER}.")


def _gemini_request(path, payload, timeout=120):
    _check_provider()
    request = Request(
        f"{GEMINI_API_BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": AI_API_KEY},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        logger.warning("Gemini request returned HTTP %s: %s", error.code, detail)
        raise RuntimeError(f"Gemini request failed (HTTP {error.code}).") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError("Unable to connect to the configured Gemini API.") from error


def _request_json(path, payload=None, timeout=60):
    _check_provider()
    headers = {"Content-Type": "application/json"}
    if AI_API_KEY:
        headers["Authorization"] = f"Bearer {AI_API_KEY}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(f"{AI_API_BASE_URL}{path}", data=data, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        logger.warning("Hosted AI request returned HTTP %s: %s", error.code, detail)
        raise RuntimeError(f"Hosted AI request failed (HTTP {error.code}).") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError("Unable to connect to the configured AI provider.") from error


def create_embeddings(texts):
    if AI_PROVIDER == "ollama":
        if hasattr(ollama, "Client"):
            response = ollama.Client(host=OLLAMA_BASE_URL).embed(model=AI_EMBEDDING_MODEL, input=texts)
        else:  # Compatibility with lightweight Ollama adapters used in tests.
            response = ollama.embed(model=AI_EMBEDDING_MODEL, input=texts)
        return response["embeddings"]
    if AI_PROVIDER == "gemini":
        embeddings = []
        for offset in range(0, len(texts), 100):
            batch = texts[offset : offset + 100]
            response = _gemini_request(
                f"/models/{AI_EMBEDDING_MODEL}:batchEmbedContents",
                {
                    "requests": [
                        {
                            "model": f"models/{AI_EMBEDDING_MODEL}",
                            "content": {"parts": [{"text": text}]},
                        }
                        for text in batch
                    ]
                },
            )
            embeddings.extend(item["values"] for item in response["embeddings"])
        return embeddings

    response = _request_json(
        "/embeddings",
        {"model": AI_EMBEDDING_MODEL, "input": texts},
        timeout=120,
    )
    return [row["embedding"] for row in sorted(response["data"], key=lambda row: row["index"])]


def stream_chat(messages):
    if AI_PROVIDER == "ollama":
        client = ollama.Client(host=OLLAMA_BASE_URL) if hasattr(ollama, "Client") else ollama
        return (
            part["message"]["content"]
            for part in client.chat(model=AI_CHAT_MODEL, messages=messages, stream=True)
        )

    if AI_PROVIDER == "gemini":
        _check_provider()
        system_messages = [item["content"] for item in messages if item.get("role") == "system"]
        contents = [
            {
                "role": "model" if item.get("role") == "assistant" else "user",
                "parts": [{"text": item["content"]}],
            }
            for item in messages
            if item.get("role") in {"user", "assistant"}
        ]
        payload = {"contents": contents}
        if system_messages:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_messages)}]}
        request = Request(
            f"{GEMINI_API_BASE_URL}/models/{AI_CHAT_MODEL}:streamGenerateContent?alt=sse",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": AI_API_KEY},
        )

        def gemini_tokens():
            try:
                with urlopen(request, timeout=180) as response:
                    for raw_line in response:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line.startswith("data:"):
                            continue
                        event = json.loads(line[5:].strip())
                        parts = event.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        for part in parts:
                            if part.get("text"):
                                yield part["text"]
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")[:500]
                logger.warning("Gemini chat returned HTTP %s: %s", error.code, detail)
                raise RuntimeError(f"Gemini chat failed (HTTP {error.code}).") from error
            except (URLError, TimeoutError) as error:
                raise RuntimeError("Unable to connect to the configured Gemini API.") from error

        return gemini_tokens()

    _check_provider()
    payload = {"model": AI_CHAT_MODEL, "messages": messages, "stream": True}
    request = Request(
        f"{AI_API_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {AI_API_KEY}"},
    )

    def tokens():
        try:
            with urlopen(request, timeout=180) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    delta = event.get("choices", [{}])[0].get("delta", {})
                    if delta.get("content"):
                        yield delta["content"]
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            logger.warning("Hosted chat returned HTTP %s: %s", error.code, detail)
            raise RuntimeError(f"Hosted AI request failed (HTTP {error.code}).") from error
        except (URLError, TimeoutError) as error:
            raise RuntimeError("Unable to connect to the configured AI provider.") from error

    return tokens()


def provider_health():
    _check_provider()
    if AI_PROVIDER == "ollama":
        client = ollama.Client(host=OLLAMA_BASE_URL)
        response = client.list()
        models = getattr(response, "models", None)
        if models is None:
            models = response.get("models", [])
        names = {(getattr(model, "model", None) or model.get("model", "")).split(":")[0] for model in models}
        chat_ready = AI_CHAT_MODEL.split(":")[0] in names
        embedding_ready = AI_EMBEDDING_MODEL.split(":")[0] in names
        return {
            "status": "healthy" if chat_ready and embedding_ready else "degraded",
            "provider": "ollama",
            "chat_model": "available" if chat_ready else "missing",
            "embedding_model": "available" if embedding_ready else "missing",
        }

    if AI_PROVIDER == "gemini":
        _check_provider()
        return {
            "status": "configured",
            "provider": "gemini",
            "chat_model": AI_CHAT_MODEL,
            "embedding_model": AI_EMBEDDING_MODEL,
        }

    return {
        "status": "healthy",
        "provider": "openai-compatible",
        "chat_model": AI_CHAT_MODEL,
        "embedding_model": AI_EMBEDDING_MODEL,
    }
