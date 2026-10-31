import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend import supabase_store as store
from backend.ai_provider import provider_health, stream_chat
from backend.auth import AuthenticatedUser, current_user
from backend.chat_memory import RECENT_MESSAGE_LIMIT, build_chat_messages
from backend.database import (
    init_db, create_chat as local_create_chat, get_chats as local_get_chats,
    get_messages as local_get_messages, get_messages_with_sources as local_get_messages_with_sources,
    add_message as local_add_message, update_chat_title as local_update_chat_title,
    chat_exists as local_chat_exists, get_recent_messages as local_get_recent_messages,
    create_document as local_create_document, get_document_by_hash as local_get_document_by_hash,
    update_document_chunk_count as local_update_document_chunk_count,
    delete_document as local_delete_document,
    get_documents as local_get_documents,
    set_chat_archived as local_set_chat_archived,
    set_message_feedback as local_set_message_feedback,
    delete_last_assistant_message as local_delete_last_assistant_message,
)
from backend.rag import index_document, remove_document_chunks, search_documents
from backend.upload_utils import UploadValidationError, cleanup_upload, save_and_validate_upload

logger = logging.getLogger(__name__)
app = FastAPI(title="AI Intelligent Chatbot API")
if not store.configured():
    init_db()

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins or ["http://localhost:5173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["Authorization", "Content-Type", "Accept"],
                   expose_headers=["X-Generation-ID"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    chat_id: str | int
    regenerate: bool = False
    action: str = Field(default="chat", pattern="^(chat|summary|key_points|quiz)$")


class RenameRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = None


class ArchiveRequest(BaseModel):
    archived: bool


class FeedbackRequest(BaseModel):
    feedback: int = Field(ge=-1, le=1)


class StopRequest(BaseModel):
    generation_id: str


_limit_lock = threading.Lock()
_request_times = {}
_generation_events = {}


def enforce_user_limit(user_id, action, limit, window_seconds):
    now = time.monotonic()
    key = (user_id, action)
    with _limit_lock:
        recent = [stamp for stamp in _request_times.get(key, []) if now - stamp < window_seconds]
        if len(recent) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit reached. Please wait and try again.")
        recent.append(now)
        _request_times[key] = recent
        if len(_request_times) > 5000:
            for old_key in list(_request_times)[:1000]:
                _request_times.pop(old_key, None)


@app.get("/")
def root():
    return {"message": "AI Intelligent Chatbot API is running"}


@app.get("/api/health")
def health_check():
    try:
        return {"backend": "available", "auth": "configured" if store.configured() else "not_configured",
                "storage": "supabase" if store.configured() else "local_ephemeral", **provider_health()}
    except Exception:
        logger.exception("Provider health check failed")
        return {"status": "degraded", "backend": "available", "provider": os.getenv("AI_PROVIDER", "ollama"),
                "ai": "unavailable or misconfigured"}


def require_owned_chat(user_id, chat_id):
    if store.configured():
        exists = store.get_chat(user_id, chat_id) is not None
    else:
        # Local development remains backward compatible; deployed auth fails closed.
        exists = local_chat_exists(chat_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Chat not found.")


def delete_local_document_data(document):
    remove_document_chunks(document[0])
    upload_name = Path(document[3]).name
    upload_roots = {
        Path(os.getenv("APP_DATA_DIR", "/tmp/chatbot-data")) / "uploads",
        Path("documents") / "uploads", Path("backend") / "uploads",
    }
    for root in upload_roots:
        (root / upload_name).unlink(missing_ok=True)
    local_delete_document(document[0])


def delete_local_chat_data(chat_id):
    for document in local_get_documents(chat_id):
        delete_local_document_data(document)
    from backend.database import delete_chat as local_delete_chat
    local_delete_chat(chat_id)


def clear_local_chat_data():
    for chat in local_get_chats(False) + local_get_chats(True):
        delete_local_chat_data(chat[0])


@app.post("/api/upload")
async def upload_document(chat_id: str = Form(...), file: UploadFile = File(...),
                          user: AuthenticatedUser = Depends(current_user)):
    require_owned_chat(user.id, chat_id)
    enforce_user_limit(user.id, "upload", int(os.getenv("UPLOADS_PER_HOUR", "20")), 3600)
    upload_dir = os.path.join(os.getenv("APP_DATA_DIR", "/tmp/chatbot-data"), "uploads")
    try:
        upload = await save_and_validate_upload(file, upload_dir)
    except UploadValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    document_id = str(uuid.uuid4())
    storage_path = f"{user.id}/{chat_id}/{document_id}/{upload.stored_filename}"
    try:
        if store.configured():
            duplicate = store.get_document_by_hash(user.id, chat_id, upload.content_hash)
            if duplicate:
                cleanup_upload(upload.file_path)
                return {"message": "This document is already attached to this chat.",
                        "filename": duplicate["original_filename"], "chunks": duplicate["chunk_count"],
                        "document_id": duplicate["id"], "duplicate": True}
            with open(upload.file_path, "rb") as source:
                store.upload_document_object(storage_path, source.read(), file.content_type)
            record = store.create_document(user.id, chat_id, upload.original_filename, storage_path,
                                           upload.size_bytes, upload.content_hash)
            document_id = record["id"]
        else:
            duplicate = local_get_document_by_hash(chat_id, upload.content_hash)
            if duplicate:
                cleanup_upload(upload.file_path)
                return {"message": "This document is already attached to this chat.",
                        "filename": duplicate[2], "chunks": duplicate[5], "document_id": duplicate[0], "duplicate": True}
            document_id = local_create_document(chat_id, upload.original_filename, upload.stored_filename,
                                                upload.size_bytes, upload.content_hash)
        indexed = index_document(upload.file_path, upload.original_filename, chat_id, document_id,
                                 owner_id=user.id if store.configured() else None)
        if store.configured():
            store.update_document_chunk_count(user.id, document_id, indexed["chunks"])
        else:
            local_update_document_chunk_count(document_id, indexed["chunks"])
        return {"message": "Document uploaded successfully", "filename": upload.original_filename,
                "chunks": indexed["chunks"], "document_id": document_id, "duplicate": False}
    except Exception as error:
        logger.exception("Document upload processing failed")
        try:
            remove_document_chunks(document_id, user.id if store.configured() else None)
            if store.configured():
                store.delete_document(user.id, document_id)
                store.delete_document_objects([storage_path])
            else:
                local_delete_document(document_id)
        except Exception:
            logger.exception("Document rollback failed")
        raise HTTPException(status_code=500, detail="Unable to process the document.") from error
    finally:
        cleanup_upload(upload.file_path)


@app.get("/api/chats/{chat_id}/documents")
def list_chat_documents(chat_id: str, user: AuthenticatedUser = Depends(current_user)):
    require_owned_chat(user.id, chat_id)
    if store.configured():
        documents = store.get_documents(user.id, chat_id)
        return {"documents": [{"id": item["id"], "chat_id": item["chat_id"],
                               "filename": item["original_filename"], "size_bytes": item["size_bytes"],
                               "chunks": item["chunk_count"], "created_at": item["created_at"]}
                              for item in documents]}
    return {"documents": [
        {"id": row[0], "chat_id": row[1], "filename": row[2], "size_bytes": row[4],
         "chunks": row[5], "created_at": row[7]} for row in local_get_documents(chat_id)
    ]}


@app.delete("/api/chats/{chat_id}/documents/{document_id}")
def remove_chat_document(chat_id: str, document_id: str,
                         user: AuthenticatedUser = Depends(current_user)):
    require_owned_chat(user.id, chat_id)
    if store.configured():
        document = store.get_document(user.id, chat_id, document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found.")
        remove_document_chunks(document_id, user.id)
        store.delete_document_objects([document["storage_path"]])
        store.delete_document(user.id, document_id)
    else:
        documents = local_get_documents(chat_id)
        document = next((row for row in documents if str(row[0]) == document_id), None)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found.")
        delete_local_document_data(document)
    return {"ok": True}


@app.post("/api/chat")
def chat(request: ChatRequest, user: AuthenticatedUser = Depends(current_user)):
    chat_id = str(request.chat_id)
    require_owned_chat(user.id, chat_id)
    enforce_user_limit(user.id, "chat", int(os.getenv("CHAT_REQUESTS_PER_MINUTE", "20")), 60)
    generation_id = str(uuid.uuid4())
    cancelled = threading.Event()
    _generation_events[generation_id] = (user.id, cancelled)
    if store.configured():
        history = store.get_messages(user.id, chat_id)
        if request.regenerate and history and history[-1]["role"] == "assistant":
            prior_user = next((item for item in reversed(history[:-1]) if item["role"] == "user"), None)
            if prior_user and prior_user["content"] == request.message:
                store.delete_last_assistant_message(user.id, chat_id)
                history = store.get_messages(user.id, chat_id)
        history_pairs = [(item["role"], item["content"]) for item in history]
        reuse_user = bool(request.regenerate and history_pairs and history_pairs[-1] == ("user", request.message))
        if reuse_user:
            user_message = history_pairs[-1][1]
            recent = history_pairs[:-1][-RECENT_MESSAGE_LIMIT:]
        else:
            user_message = request.message
            recent = history_pairs[-RECENT_MESSAGE_LIMIT:]
        add = lambda role, content, sources=None: store.add_message(user.id, chat_id, role, content, sources)
        if not history:
            title = user_message.strip()[:40] or "New Conversation"
            store.update_chat_title(user.id, chat_id, title)
    else:
        history = local_get_messages(chat_id)
        if request.regenerate and history and history[-1][0] == "assistant":
            prior_user = next((item for item in reversed(history[:-1]) if item[0] == "user"), None)
            if prior_user and prior_user[1] == request.message:
                local_delete_last_assistant_message(chat_id)
                history = local_get_messages(chat_id)
        reuse_user = bool(request.regenerate and history and history[-1] == ("user", request.message))
        if reuse_user:
            user_message = history[-1][1]
            recent = history[:-1][-RECENT_MESSAGE_LIMIT:]
        else:
            user_message = request.message
            recent = history[-RECENT_MESSAGE_LIMIT:]
        add = lambda role, content, sources=None: local_add_message(chat_id, role, content, json.dumps(sources or []))
        if not history:
            local_update_chat_title(chat_id, user_message.strip()[:40] or "New Conversation")
    if not reuse_user:
        add("user", user_message)
    action_prompts = {
        "summary": "Summarize the uploaded documents. Organize the summary under clear headings and only use available document evidence.",
        "key_points": "Extract the most important key points from the uploaded documents as a concise numbered list, using only available document evidence.",
        "quiz": "Create a 5-question quiz from the uploaded documents. Include an answer key after the questions and use only available document evidence.",
    }
    question = action_prompts.get(request.action, user_message)
    try:
        chunks = search_documents(question, chat_id, top_k=5, owner_id=user.id if store.configured() else None)
    except Exception:
        logger.exception("Document retrieval failed")
        chunks = []
    context = "\n\n".join(f"Source: {item['filename']}\n{item['text']}" for item in chunks)
    sources = [{"document_id": item["document_id"], "filename": item["filename"],
                "chunk": item["chunk"], **({"page": item["page"]} if item.get("page") else {})}
               for item in chunks]
    prompt = build_chat_messages(recent, question, context)

    def generate():
        response = ""
        iterator = iter(stream_chat(prompt))
        try:
            for token in iterator:
                if cancelled.is_set():
                    break
                response += token
                yield json.dumps({"token": token}) + "\n"
        except GeneratorExit:
            cancelled.set()
            if response:
                add("assistant", response, sources)
            raise
        except Exception:
            logger.exception("AI response generation failed")
            yield json.dumps({"error": "AI response failed. Check the configured AI provider and model settings."}) + "\n"
            return
        finally:
            close = getattr(iterator, "close", None)
            if close:
                close()
            _generation_events.pop(generation_id, None)
        add("assistant", response, sources)
        if not cancelled.is_set():
            yield json.dumps({"sources": sources}) + "\n"
    return StreamingResponse(generate(), media_type="application/x-ndjson",
                             headers={"X-Generation-ID": generation_id})


@app.post("/api/chat/stop")
def stop_chat_generation(body: StopRequest, user: AuthenticatedUser = Depends(current_user)):
    generation = _generation_events.get(body.generation_id)
    if not generation or generation[0] != user.id:
        raise HTTPException(status_code=404, detail="Generation not found.")
    generation[1].set()
    return {"stopping": True}


@app.post("/api/new-chat")
def new_chat(user: AuthenticatedUser = Depends(current_user)):
    record = store.create_chat(user.id) if store.configured() else None
    chat_id = record["id"] if record else local_create_chat()
    return {"message": "New conversation started", "chat_id": chat_id, "title": "New Conversation"}


@app.get("/api/chats")
def get_all_chats(archived: bool = False, user: AuthenticatedUser = Depends(current_user)):
    if store.configured():
        chats = store.get_chats(user.id, archived)
        return {"chats": chats}
    return {"chats": [{"id": row[0], "title": row[1], "created_at": row[2], "archived": bool(row[3])}
                       for row in local_get_chats(archived)]}


@app.get("/api/chats/export")
def export_chats(user: AuthenticatedUser = Depends(current_user)):
    if store.configured():
        chats = store.get_chats(user.id, False) + store.get_chats(user.id, True)
        result = [{"id": chat["id"], "title": chat["title"],
                   "messages": [{"role": row["role"], "content": row["content"],
                                 "sources": row.get("sources", [])}
                                for row in store.get_messages(user.id, chat["id"]) ]}
                  for chat in chats]
    else:
        local_chats = local_get_chats(False) + local_get_chats(True)
        result = [{"id": row[0], "title": row[1], "messages": local_get_messages_with_sources(row[0])}
                  for row in local_chats]
    return {"chats": result}


@app.get("/api/chats/{chat_id}")
def get_chat_messages(chat_id: str, user: AuthenticatedUser = Depends(current_user)):
    require_owned_chat(user.id, chat_id)
    if store.configured():
        rows = store.get_messages(user.id, chat_id)
        messages = [{"id": row["id"], "role": row["role"], "content": row["content"],
                     "sources": row.get("sources", []), "feedback": row.get("feedback")}
                    for row in rows]
    else:
        messages = local_get_messages_with_sources(chat_id)
    return {"chat_id": chat_id, "messages": messages}


@app.patch("/api/chats/{chat_id}")
def rename_chat(chat_id: str, body: RenameRequest, user: AuthenticatedUser = Depends(current_user)):
    require_owned_chat(user.id, chat_id)
    if body.title is None and body.archived is None:
        raise HTTPException(status_code=422, detail="Set a title or archive state.")
    if body.title is not None:
        if not store.configured():
            local_update_chat_title(chat_id, body.title.strip())
        else:
            store.update_chat_title(user.id, chat_id, body.title.strip())
    if body.archived is not None:
        if not store.configured():
            local_set_chat_archived(chat_id, body.archived)
        else:
            store.set_chat_archived(user.id, chat_id, body.archived)
    return {"ok": True}


@app.patch("/api/chats/{chat_id}/messages/{message_id}/feedback")
def message_feedback(chat_id: str, message_id: str, body: FeedbackRequest,
                     user: AuthenticatedUser = Depends(current_user)):
    require_owned_chat(user.id, chat_id)
    if body.feedback not in {-1, 1}:
        raise HTTPException(status_code=422, detail="Feedback must be 1 or -1.")
    if store.configured():
        rows = store.get_messages(user.id, chat_id)
        if not any(str(row["id"]) == message_id and row["role"] == "assistant" for row in rows):
            raise HTTPException(status_code=404, detail="Assistant message not found.")
        store.set_message_feedback(user.id, chat_id, message_id, body.feedback)
    else:
        if not local_set_message_feedback(chat_id, int(message_id), body.feedback):
            raise HTTPException(status_code=404, detail="Message not found.")
    return {"ok": True}


@app.delete("/api/chats/{chat_id}")
def remove_chat(chat_id: str, user: AuthenticatedUser = Depends(current_user)):
    require_owned_chat(user.id, chat_id)
    if store.configured():
        store.delete_chat(user.id, chat_id)
    else:
        delete_local_chat_data(chat_id)
    return {"ok": True}


@app.delete("/api/chats")
def clear_chats(user: AuthenticatedUser = Depends(current_user)):
    if store.configured():
        store.delete_all_chats(user.id)
    else:
        clear_local_chat_data()
    return {"ok": True}


@app.delete("/api/account")
def delete_account(user: AuthenticatedUser = Depends(current_user)):
    if store.configured():
        store.delete_user_data(user.id)
    else:
        clear_local_chat_data()
    return {"ok": True}
