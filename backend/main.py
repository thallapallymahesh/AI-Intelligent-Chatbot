import json
import logging
import os
import uuid

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
)
from backend.rag import index_document, remove_document_chunks, search_documents
from backend.upload_utils import UploadValidationError, cleanup_upload, save_and_validate_upload

logger = logging.getLogger(__name__)
app = FastAPI(title="AI Intelligent Chatbot API")
if not store.configured():
    init_db()

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins or ["http://localhost:5173"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["Authorization", "Content-Type", "Accept"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    chat_id: str


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


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


@app.post("/api/upload")
async def upload_document(chat_id: str = Form(...), file: UploadFile = File(...),
                          user: AuthenticatedUser = Depends(current_user)):
    require_owned_chat(user.id, chat_id)
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


@app.post("/api/chat")
def chat(request: ChatRequest, user: AuthenticatedUser = Depends(current_user)):
    chat_id = request.chat_id
    require_owned_chat(user.id, chat_id)
    if store.configured():
        old_messages = store.get_messages(user.id, chat_id)
        recent = store.get_recent_messages(user.id, chat_id, RECENT_MESSAGE_LIMIT)
        add = lambda role, content, sources=None: store.add_message(user.id, chat_id, role, content, sources)
        if not old_messages:
            title = request.message.strip()[:40] or "New Conversation"
            store.update_chat_title(user.id, chat_id, title)
    else:
        old_messages = local_get_messages(chat_id)
        recent = local_get_recent_messages(chat_id, RECENT_MESSAGE_LIMIT)
        add = lambda role, content, sources=None: local_add_message(chat_id, role, content, json.dumps(sources or []))
        if not old_messages:
            local_update_chat_title(chat_id, request.message.strip()[:40] or "New Conversation")
    add("user", request.message)
    try:
        chunks = search_documents(request.message, chat_id, top_k=3, owner_id=user.id if store.configured() else None)
    except Exception:
        logger.exception("Document retrieval failed")
        chunks = []
    context = "\n\n".join(f"Source: {item['filename']}\n{item['text']}" for item in chunks)
    sources = [{"document_id": item["document_id"], "filename": item["filename"], "chunk": item["chunk"]} for item in chunks]
    prompt = build_chat_messages(recent, request.message, context)

    def generate():
        response = ""
        try:
            for token in stream_chat(prompt):
                response += token
                yield json.dumps({"token": token}) + "\n"
        except Exception:
            logger.exception("AI response generation failed")
            yield json.dumps({"error": "AI response failed. Check the configured AI provider and model settings."}) + "\n"
            return
        add("assistant", response, sources)
        yield json.dumps({"sources": sources}) + "\n"
    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.post("/api/new-chat")
def new_chat(user: AuthenticatedUser = Depends(current_user)):
    record = store.create_chat(user.id) if store.configured() else None
    chat_id = record["id"] if record else local_create_chat()
    return {"message": "New conversation started", "chat_id": chat_id, "title": "New Conversation"}


@app.get("/api/chats")
def get_all_chats(user: AuthenticatedUser = Depends(current_user)):
    if store.configured():
        chats = store.get_chats(user.id)
        return {"chats": chats}
    return {"chats": [{"id": row[0], "title": row[1], "created_at": row[2]} for row in local_get_chats()]}


@app.get("/api/chats/{chat_id}")
def get_chat_messages(chat_id: str, user: AuthenticatedUser = Depends(current_user)):
    require_owned_chat(user.id, chat_id)
    if store.configured():
        rows = store.get_messages(user.id, chat_id)
        messages = [{"role": row["role"], "content": row["content"], "sources": row.get("sources", [])} for row in rows]
    else:
        messages = local_get_messages_with_sources(chat_id)
    return {"chat_id": chat_id, "messages": messages}


@app.patch("/api/chats/{chat_id}")
def rename_chat(chat_id: str, body: RenameRequest, user: AuthenticatedUser = Depends(current_user)):
    require_owned_chat(user.id, chat_id)
    if not store.configured():
        local_update_chat_title(chat_id, body.title.strip())
    else:
        store.update_chat_title(user.id, chat_id, body.title.strip())
    return {"ok": True}


@app.delete("/api/chats/{chat_id}")
def remove_chat(chat_id: str, user: AuthenticatedUser = Depends(current_user)):
    require_owned_chat(user.id, chat_id)
    if store.configured():
        store.delete_chat(user.id, chat_id)
    else:
        from backend.database import delete_chat as local_delete_chat
        local_delete_chat(chat_id)
    return {"ok": True}


@app.delete("/api/chats")
def clear_chats(user: AuthenticatedUser = Depends(current_user)):
    if store.configured():
        store.delete_all_chats(user.id)
    else:
        from backend.database import delete_all_chats as local_delete_all_chats
        local_delete_all_chats()
    return {"ok": True}
