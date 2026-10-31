import os
import uuid
from backend.ai_provider import create_embeddings as provider_create_embeddings
from backend import supabase_store

from pypdf import PdfReader
from docx import Document

# Chroma is retained for local development; production with Supabase uses pgvector.
DATA_DIR = os.getenv("APP_DATA_DIR", "./backend")
CHROMA_DIR = os.getenv("CHROMA_DIR", os.path.join(DATA_DIR, "chroma_db"))
collection = None
if not supabase_store.configured():
    import chromadb
    os.makedirs(CHROMA_DIR, exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = chroma_client.get_or_create_collection(name="documents")


def extract_text(file_path):
    """
    Extract text from PDF, DOCX or TXT files.
    """

    extension = os.path.splitext(file_path)[1].lower()

    if extension == ".pdf":
        reader = PdfReader(file_path)

        text = ""

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                text += page_text + "\n"

        return text

    elif extension == ".docx":
        document = Document(file_path)

        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    elif extension == ".txt":
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()

    else:
        raise ValueError("Unsupported file type. " "Use PDF, DOCX or TXT.")


def extract_pages(file_path):
    """Return text units with source page numbers when the format has pages."""
    extension = os.path.splitext(file_path)[1].lower()
    if extension == ".pdf":
        reader = PdfReader(file_path)
        return [(number, page.extract_text() or "")
                for number, page in enumerate(reader.pages, start=1)]
    if extension == ".docx":
        document = Document(file_path)
        return [(None, "\n".join(paragraph.text for paragraph in document.paragraphs))]
    if extension == ".txt":
        with open(file_path, "r", encoding="utf-8") as source:
            return [(None, source.read())]
    raise ValueError("Unsupported file type. Use PDF, DOCX or TXT.")


def chunk_text(text, chunk_size=800, overlap=100):
    """
    Split document text into smaller chunks.
    """

    text = text.strip()

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunk = text[start:end]

        if chunk.strip():
            chunks.append(chunk.strip())

        start += chunk_size - overlap

    return chunks


def create_embeddings(texts):
    """
    Generate embeddings using Ollama.
    """

    return provider_create_embeddings(texts)


def index_document(file_path, filename, chat_id, document_id, owner_id=None):
    """
    Process and store a document in ChromaDB.
    """

    pages = extract_pages(file_path)
    if not any(text.strip() for _, text in pages):
        raise ValueError("No readable text found in the document.")
    chunk_records = [(chunk, page_number) for page_number, text in pages
                     for chunk in chunk_text(text)]
    chunks = [chunk for chunk, _ in chunk_records]
    page_numbers = [page_number for _, page_number in chunk_records]

    embeddings = create_embeddings(chunks)

    if owner_id and supabase_store.configured():
        supabase_store.insert_document_chunks(
            owner_id, chat_id, document_id, filename, chunks, embeddings, page_numbers
        )
        return {"filename": filename, "chunks": len(chunks)}

    ids = [str(uuid.uuid4()) for _ in chunks]

    metadatas = [
        {
            "chat_id": chat_id,
            "document_id": document_id,
            "filename": filename,
            "chunk": index,
            **({"page": page_numbers[index]} if page_numbers[index] else {}),
        }
        for index in range(len(chunks))
    ]

    collection.add(
        ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas
    )

    return {"filename": filename, "chunks": len(chunks)}


def remove_document_chunks(document_id, owner_id=None):
    if owner_id and supabase_store.configured():
        return supabase_store.remove_document_chunks(document_id, owner_id)
    collection.delete(where={"document_id": document_id})


def search_documents(query, chat_id, top_k=3, owner_id=None):
    """
    Find relevant document chunks for a user question.
    """

    query_embedding = create_embeddings([query])[0]

    if owner_id and supabase_store.configured():
        matches = supabase_store.search_document_chunks(
            owner_id, chat_id, query_embedding, top_k
        )
        return [{"text": row["content"], "document_id": row["document_id"],
                 "filename": row["filename"], "chunk": row["chunk_index"],
                 "page": row.get("page_number")}
                for row in matches]

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"chat_id": chat_id},
    )

    documents = results.get("documents", [[]])[0]

    metadatas = results.get("metadatas", [[]])[0]

    sources = []

    for document, metadata in zip(documents, metadatas):
        sources.append(
            {
                "text": document,
                "document_id": metadata.get("document_id"),
                "filename": metadata.get("filename", "Unknown"),
                "chunk": metadata.get("chunk", 0),
                "page": metadata.get("page"),
            }
        )

    return sources
