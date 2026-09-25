import json
import sqlite3

DB_PATH = "backend/chatbot.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id)
        )
    """)

    # Add persisted citations without changing existing message content.
    message_columns = {
        column[1] for column in cursor.execute("PRAGMA table_info(messages)")
    }

    if "sources_json" not in message_columns:
        cursor.execute(
            "ALTER TABLE messages ADD COLUMN sources_json TEXT NOT NULL DEFAULT '[]'"
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL UNIQUE,
            size_bytes INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            content_hash TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
    """)

    document_columns = {
        column[1] for column in cursor.execute("PRAGMA table_info(documents)")
    }

    if "content_hash" not in document_columns:
        cursor.execute(
            "ALTER TABLE documents ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''"
        )

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_chat_content_hash
        ON documents (chat_id, content_hash)
    """)

    conn.commit()
    conn.close()


def create_chat(title="New Conversation"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("INSERT INTO chats (title) VALUES (?)", (title,))

    chat_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return chat_id


def update_chat_title(chat_id, title):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))

    conn.commit()
    conn.close()


def add_message(chat_id, role, content, sources_json="[]"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO messages (chat_id, role, content, sources_json)
        VALUES (?, ?, ?, ?)
        """,
        (chat_id, role, content, sources_json),
    )

    conn.commit()
    conn.close()


def get_chats():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, created_at
        FROM chats
        ORDER BY created_at DESC
        """)

    chats = cursor.fetchall()

    conn.close()

    return chats


def get_messages(chat_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, content
        FROM messages
        WHERE chat_id = ?
        ORDER BY id ASC
        """,
        (chat_id,),
    )

    messages = cursor.fetchall()

    conn.close()

    return messages


def get_messages_with_sources(chat_id):
    """Return saved messages plus their persisted document sources."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, content, sources_json
        FROM messages
        WHERE chat_id = ?
        ORDER BY id ASC
        """,
        (chat_id,),
    )

    messages = []
    for role, content, sources_json in cursor.fetchall():
        try:
            sources = json.loads(sources_json or "[]")
        except json.JSONDecodeError:
            sources = []

        messages.append(
            {
                "role": role,
                "content": content,
                "sources": sources if isinstance(sources, list) else [],
            }
        )

    conn.close()

    return messages


def get_recent_messages(chat_id, limit):
    if limit <= 0:
        return []

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT role, content
        FROM (
            SELECT id, role, content
            FROM messages
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
        )
        ORDER BY id ASC
        """,
        (chat_id, limit),
    )

    messages = cursor.fetchall()

    conn.close()

    return messages


def chat_exists(chat_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM chats WHERE id = ?", (chat_id,))

    exists = cursor.fetchone() is not None

    conn.close()

    return exists


def create_document(
    chat_id,
    original_filename,
    stored_filename,
    size_bytes,
    content_hash,
    chunk_count=0,
):
    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO documents (
                chat_id,
                original_filename,
                stored_filename,
                size_bytes,
                content_hash,
                chunk_count
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id,
                original_filename,
                stored_filename,
                size_bytes,
                content_hash,
                chunk_count,
            ),
        )

        document_id = cursor.lastrowid

        conn.commit()

        return document_id
    finally:
        conn.close()


def get_documents(chat_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, chat_id, original_filename, stored_filename,
               size_bytes, chunk_count, content_hash, created_at
        FROM documents
        WHERE chat_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (chat_id,),
    )

    documents = cursor.fetchall()

    conn.close()

    return documents


def update_document_chunk_count(document_id, chunk_count):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE documents SET chunk_count = ? WHERE id = ?",
        (chunk_count, document_id),
    )

    conn.commit()
    conn.close()


def get_document_by_hash(chat_id, content_hash):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, chat_id, original_filename, stored_filename,
               size_bytes, chunk_count, content_hash, created_at
        FROM documents
        WHERE chat_id = ? AND content_hash = ?
        """,
        (chat_id, content_hash),
    )

    document = cursor.fetchone()

    conn.close()

    return document


def delete_document(document_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    conn.commit()
    conn.close()
