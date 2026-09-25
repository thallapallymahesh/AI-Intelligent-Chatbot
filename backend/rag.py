import os
import uuid
import ollama
import chromadb

from pypdf import PdfReader
from docx import Document

# Persistent vector database
chroma_client = chromadb.PersistentClient(path="./backend/chroma_db")

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

    response = ollama.embed(model="nomic-embed-text", input=texts)

    return response["embeddings"]


def index_document(file_path, filename, chat_id, document_id):
    """
    Process and store a document in ChromaDB.
    """

    text = extract_text(file_path)

    if not text.strip():
        raise ValueError("No readable text found in the document.")

    chunks = chunk_text(text)

    embeddings = create_embeddings(chunks)

    ids = [str(uuid.uuid4()) for _ in chunks]

    metadatas = [
        {
            "chat_id": chat_id,
            "document_id": document_id,
            "filename": filename,
            "chunk": index,
        }
        for index in range(len(chunks))
    ]

    collection.add(
        ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas
    )

    return {"filename": filename, "chunks": len(chunks)}


def remove_document_chunks(document_id):
    collection.delete(where={"document_id": document_id})


def search_documents(query, chat_id, top_k=3):
    """
    Find relevant document chunks for a user question.
    """

    query_embedding = create_embeddings([query])[0]

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
            }
        )

    return sources
