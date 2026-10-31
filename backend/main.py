import json
import logging
import os

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse

from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from backend.rag import index_document, remove_document_chunks, search_documents
from backend.ai_provider import provider_health, stream_chat
from backend.chat_memory import RECENT_MESSAGE_LIMIT, build_chat_messages
from backend.database import (
    init_db,
    create_chat,
    get_chats,
    get_messages,
    get_messages_with_sources,
    add_message,
    update_chat_title,
    chat_exists,
    get_recent_messages,
    create_document,
    get_document_by_hash,
    update_document_chunk_count,
    delete_document,
)
from backend.upload_utils import (
    UploadValidationError,
    cleanup_upload,
    save_and_validate_upload,
)

app = FastAPI(title="AI Intelligent Chatbot API")
init_db()
logger = logging.getLogger(__name__)


# --------------------------------------------------
# CORS
# --------------------------------------------------

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:5176",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Request model
# --------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    chat_id: int


# --------------------------------------------------
# Home
# --------------------------------------------------


@app.get("/")
def root():

    return {"message": "AI Intelligent Chatbot API is running"}


# --------------------------------------------------
# Health
# --------------------------------------------------


@app.get("/api/health")
def health_check():
    try:
        return {"backend": "available", **provider_health()}
    except Exception:
        logger.exception("AI provider health check failed")
        return {
            "status": "degraded",
            "backend": "available",
            "provider": os.getenv("AI_PROVIDER", "ollama"),
            "ai": "unavailable or misconfigured",
        }


# --------------------------------------------------
# Upload document
# --------------------------------------------------


@app.post("/api/upload")
async def upload_document(
    chat_id: int = Form(...),
    file: UploadFile = File(...),
):
    if not chat_exists(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found.")

    try:
        upload_dir = os.path.join(os.getenv("APP_DATA_DIR", "documents"), "uploads")
        stored_upload = await save_and_validate_upload(file, upload_dir)
    except UploadValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error))

    existing_document = get_document_by_hash(chat_id, stored_upload.content_hash)

    if existing_document:
        cleanup_upload(stored_upload.file_path)

        return {
            "message": "This document is already attached to this chat.",
            "filename": existing_document[2],
            "chunks": existing_document[5],
            "document_id": existing_document[0],
            "duplicate": True,
        }

    document_id = None

    try:
        document_id = create_document(
            chat_id,
            stored_upload.original_filename,
            stored_upload.stored_filename,
            stored_upload.size_bytes,
            stored_upload.content_hash,
        )

        result = index_document(
            stored_upload.file_path,
            stored_upload.original_filename,
            chat_id,
            document_id,
        )

        update_document_chunk_count(document_id, result["chunks"])

        return {
            "message": "Document uploaded successfully",
            "filename": stored_upload.original_filename,
            "chunks": result["chunks"],
            "document_id": document_id,
            "duplicate": False,
        }
    except Exception:
        logger.exception("Document upload processing failed")
        if document_id is not None:
            try:
                remove_document_chunks(document_id)
            finally:
                delete_document(document_id)

        cleanup_upload(stored_upload.file_path)

        raise HTTPException(status_code=500, detail="Unable to process the document.")


# --------------------------------------------------
# Chat
# --------------------------------------------------


@app.post("/api/chat")
def chat(request: ChatRequest):

    user_message = request.message
    chat_id = request.chat_id

    if not chat_exists(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found.")

    # Read this chat's saved history before adding the new message.
    existing_messages = get_messages(chat_id)
    recent_messages = get_recent_messages(chat_id, RECENT_MESSAGE_LIMIT)

    # Save user message
    add_message(chat_id, "user", user_message)

    # Give the chat a title from the first question
    if len(existing_messages) == 0:
        title = user_message.strip()

        if len(title) > 40:
            title = title[:40] + "..."

        update_chat_title(chat_id, title)

    # Search relevant document chunks
    try:
        relevant_chunks = search_documents(user_message, chat_id, top_k=3)
    except Exception:
        # A RAG outage should not prevent normal AI chat from working.
        logger.exception("RAG search failed for chat %s", chat_id)
        relevant_chunks = []

    context = "\n\n".join(
        [
            f"Source: {chunk['filename']}\n" f"{chunk['text']}"
            for chunk in relevant_chunks
        ]
    )

    sources = [
        {
            "document_id": chunk["document_id"],
            "filename": chunk["filename"],
            "chunk": chunk["chunk"],
        }
        for chunk in relevant_chunks
    ]

    ollama_messages = build_chat_messages(
        recent_messages,
        user_message,
        context,
    )

    def generate():

        full_response = ""

        try:
            for text in stream_chat(ollama_messages):
                full_response += text
                yield json.dumps({"token": text}) + "\n"
        except Exception:
            logger.exception("Ollama chat failed for chat %s", chat_id)
            if full_response:
                add_message(chat_id, "assistant", full_response, json.dumps(sources))
            yield json.dumps(
                {"error": "AI response failed. Check the configured AI provider and model settings."}
            ) + "\n"
            return

        # Save the answer and its sources together so reopening a chat preserves them.
        add_message(chat_id, "assistant", full_response, json.dumps(sources))
        yield json.dumps({"sources": sources}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


# --------------------------------------------------
# New Chat
# --------------------------------------------------


@app.post("/api/new-chat")
def new_chat():
    chat_id = create_chat("New Conversation")

    return {
        "message": "New conversation started",
        "chat_id": chat_id,
        "title": "New Conversation",
    }


# --------------------------------------------------
# Get all chats
# --------------------------------------------------


@app.get("/api/chats")
def get_all_chats():

    chats = get_chats()

    return {
        "chats": [
            {
                "id": chat[0],
                "title": chat[1],
                "created_at": chat[2],
            }
            for chat in chats
        ]
    }


# --------------------------------------------------
# Get messages from a chat
# --------------------------------------------------


@app.get("/api/chats/{chat_id}")
def get_chat_messages(chat_id: int):
    if not chat_exists(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found.")

    return {
        "chat_id": chat_id,
        "messages": get_messages_with_sources(chat_id),
    }
