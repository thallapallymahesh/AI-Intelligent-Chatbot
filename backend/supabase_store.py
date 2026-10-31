"""Server-side Supabase Auth, PostgREST, Storage, and pgvector helpers.

Only the backend reads the service-role key. Every data operation includes the
verified owner id, while SQL RLS policies provide an additional boundary for
direct client access.
"""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class SupabaseError(RuntimeError):
    pass


class AuthenticationError(SupabaseError):
    pass


def _settings():
    return (
        os.getenv("SUPABASE_URL", "").rstrip("/"),
        os.getenv("SUPABASE_ANON_KEY", ""),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
    )


def configured():
    return all(_settings())


def _request(path, method="GET", *, payload=None, params=None, token=None,
             admin=False, content_type="application/json", raw_body=None):
    base_url, anon_key, service_key = _settings()
    if not base_url or not anon_key or (admin and not service_key):
        raise SupabaseError("Supabase is not configured.")
    query = f"?{urlencode(params, doseq=True)}" if params else ""
    key = service_key if admin else anon_key
    headers = {"apikey": key, "Authorization": f"Bearer {token or key}"}
    if content_type:
        headers["Content-Type"] = content_type
    if admin and path.startswith("/rest/v1/"):
        headers["Prefer"] = "return=representation"
    body = raw_body if raw_body is not None else (
        json.dumps(payload).encode("utf-8") if payload is not None else None
    )
    request = Request(f"{base_url}{path}{query}", data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            data = response.read()
            return json.loads(data.decode("utf-8")) if data else None
    except HTTPError as error:
        if path == "/auth/v1/user":
            raise AuthenticationError("Supabase rejected the access token.") from error
        raise SupabaseError(f"Supabase request failed (HTTP {error.code}).") from error
    except (URLError, TimeoutError) as error:
        raise SupabaseError("Unable to connect to Supabase.") from error


def verify_access_token(access_token):
    user = _request("/auth/v1/user", token=access_token)
    if not isinstance(user, dict) or not user.get("id"):
        raise AuthenticationError("Supabase returned no user for the access token.")
    return user


def _rows(table, *, owner_id, filters=None, select="*", order=None):
    params = {"select": select, "owner_id": f"eq.{owner_id}"}
    params.update(filters or {})
    if order:
        params["order"] = order
    result = _request(f"/rest/v1/{table}", params=params, admin=True)
    return result if isinstance(result, list) else []


def _insert(table, payload):
    rows = _request(f"/rest/v1/{table}", "POST", payload=payload, admin=True)
    if not rows:
        raise SupabaseError("Supabase did not return the inserted record.")
    return rows[0]


def _patch(table, *, owner_id, filters, payload):
    params = {"owner_id": f"eq.{owner_id}", **filters}
    return _request(f"/rest/v1/{table}", "PATCH", params=params,
                    payload=payload, admin=True)


def _delete(table, *, owner_id, filters):
    params = {"owner_id": f"eq.{owner_id}", **filters}
    return _request(f"/rest/v1/{table}", "DELETE", params=params, admin=True)


def create_chat(owner_id, title="New Conversation"):
    return _insert("chats", {"owner_id": owner_id, "title": title})


def get_chats(owner_id):
    return _rows("chats", owner_id=owner_id,
                 select="id,title,created_at,updated_at", order="updated_at.desc")


def get_chat(owner_id, chat_id):
    rows = _rows("chats", owner_id=owner_id,
                 filters={"id": f"eq.{chat_id}"}, select="id,title,created_at")
    return rows[0] if rows else None


def get_messages(owner_id, chat_id):
    return _rows("messages", owner_id=owner_id,
                 filters={"chat_id": f"eq.{chat_id}"},
                 select="id,role,content,sources,created_at", order="created_at.asc")


def get_recent_messages(owner_id, chat_id, limit):
    if limit <= 0:
        return []
    rows = _rows("messages", owner_id=owner_id,
                 filters={"chat_id": f"eq.{chat_id}"},
                 select="role,content,created_at", order="created_at.desc")
    return [(row["role"], row["content"]) for row in reversed(rows[:limit])]


def add_message(owner_id, chat_id, role, content, sources=None):
    return _insert("messages", {
        "owner_id": owner_id, "chat_id": chat_id, "role": role,
        "content": content, "sources": sources or [],
    })


def update_chat_title(owner_id, chat_id, title):
    return _patch("chats", owner_id=owner_id, filters={"id": f"eq.{chat_id}"},
                  payload={"title": title})


def get_document_by_hash(owner_id, chat_id, content_hash):
    rows = _rows("documents", owner_id=owner_id, filters={
        "chat_id": f"eq.{chat_id}", "content_hash": f"eq.{content_hash}"
    })
    return rows[0] if rows else None


def create_document(owner_id, chat_id, original_filename, storage_path,
                    size_bytes, content_hash, chunk_count=0):
    return _insert("documents", {
        "owner_id": owner_id, "chat_id": chat_id,
        "original_filename": original_filename, "storage_path": storage_path,
        "size_bytes": size_bytes, "content_hash": content_hash,
        "chunk_count": chunk_count,
    })


def update_document_chunk_count(owner_id, document_id, chunk_count):
    return _patch("documents", owner_id=owner_id,
                  filters={"id": f"eq.{document_id}"},
                  payload={"chunk_count": chunk_count})


def delete_document(owner_id, document_id):
    return _delete("documents", owner_id=owner_id,
                   filters={"id": f"eq.{document_id}"})


def insert_document_chunks(owner_id, chat_id, document_id, filename, chunks, embeddings):
    rows = [{
        "owner_id": owner_id,
        "chat_id": chat_id,
        "document_id": document_id,
        "filename": filename,
        "chunk_index": index,
        "content": content,
        "embedding": "[" + ",".join(str(float(value)) for value in vector) + "]",
    } for index, (content, vector) in enumerate(zip(chunks, embeddings))]
    if rows:
        _request("/rest/v1/document_chunks", "POST", payload=rows, admin=True)


def remove_document_chunks(document_id, owner_id):
    return _delete("document_chunks", owner_id=owner_id,
                   filters={"document_id": f"eq.{document_id}"})


def search_document_chunks(owner_id, chat_id, embedding, top_k):
    vector = "[" + ",".join(str(float(value)) for value in embedding) + "]"
    return _request("/rest/v1/rpc/match_document_chunks", "POST", admin=True,
                    payload={"query_embedding": vector, "match_chat_id": chat_id,
                             "match_owner_id": owner_id, "match_count": top_k}) or []


def upload_document_object(path, content, content_type):
    safe_path = quote(path, safe="/")
    return _request(f"/storage/v1/object/user-documents/{safe_path}", "POST",
                    admin=True, content_type=content_type or "application/octet-stream",
                    raw_body=content)


def delete_document_objects(paths):
    if not paths:
        return
    return _request("/storage/v1/object/user-documents", "DELETE", admin=True,
                    payload={"prefixes": paths})


def delete_chat(owner_id, chat_id):
    documents = _rows("documents", owner_id=owner_id,
                      filters={"chat_id": f"eq.{chat_id}"}, select="storage_path")
    delete_document_objects([row["storage_path"] for row in documents])
    return _delete("chats", owner_id=owner_id, filters={"id": f"eq.{chat_id}"})


def delete_all_chats(owner_id):
    for chat in get_chats(owner_id):
        delete_chat(owner_id, chat["id"])
