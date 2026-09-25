import asyncio
import hashlib
import importlib
import io
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest import mock

from backend import database
from docx import Document
from pypdf import PdfWriter
from backend.upload_utils import (
    MAX_UPLOAD_BYTES,
    UploadValidationError,
    cleanup_upload,
    save_and_validate_upload,
)


class AsyncUpload:
    def __init__(self, filename, content):
        self.filename = filename
        self.content = content
        self.position = 0

    async def read(self, size):
        chunk = self.content[self.position : self.position + size]
        self.position += len(chunk)
        return chunk


class FakeCollection:
    def __init__(self):
        self.add_calls = []
        self.query_calls = []
        self.deleted_filters = []

    def add(self, **kwargs):
        self.add_calls.append(kwargs)

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {
            "documents": [["Selected chat document"]],
            "metadatas": [
                [
                    {
                        "chat_id": 2,
                        "document_id": 9,
                        "filename": "selected.txt",
                        "chunk": 0,
                    }
                ]
            ],
        }

    def delete(self, **kwargs):
        self.deleted_filters.append(kwargs)


class FakeChromaClient:
    def __init__(self, collection):
        self.collection = collection

    def get_or_create_collection(self, name):
        return self.collection


class DocumentUploadTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.upload_directory = Path(self.temporary_directory.name) / "uploads"
        self.original_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.temporary_directory.name, "test.db")
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temporary_directory.cleanup()

    def test_text_upload_uses_safe_generated_name_and_hash(self):
        content = b"Hello from a safe text upload."
        upload = AsyncUpload("..\\unsafe\\notes.txt", content)

        stored = asyncio.run(save_and_validate_upload(upload, self.upload_directory))

        self.assertEqual(stored.original_filename, "notes.txt")
        self.assertNotEqual(stored.stored_filename, stored.original_filename)
        self.assertTrue(stored.file_path.exists())
        self.assertEqual(stored.size_bytes, len(content))
        self.assertEqual(stored.content_hash, hashlib.sha256(content).hexdigest())

        cleanup_upload(stored.file_path)

    def test_supported_file_types_are_accepted(self):
        pdf_buffer = io.BytesIO()
        pdf_writer = PdfWriter()
        pdf_writer.add_blank_page(width=72, height=72)
        pdf_writer.write(pdf_buffer)

        docx_buffer = io.BytesIO()
        docx_document = Document()
        docx_document.add_paragraph("Safe DOCX content")
        docx_document.save(docx_buffer)

        uploads = [
            AsyncUpload("valid.pdf", pdf_buffer.getvalue()),
            AsyncUpload("valid.docx", docx_buffer.getvalue()),
            AsyncUpload("valid.txt", b"Safe text content"),
        ]

        for upload in uploads:
            stored = asyncio.run(save_and_validate_upload(upload, self.upload_directory))
            self.assertTrue(stored.file_path.exists())
            cleanup_upload(stored.file_path)

    def test_invalid_file_contents_are_rejected_and_cleaned_up(self):
        upload = AsyncUpload("not-a-pdf.pdf", b"This is not a PDF")

        with self.assertRaises(UploadValidationError) as error:
            asyncio.run(save_and_validate_upload(upload, self.upload_directory))

        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(list(self.upload_directory.glob("*")), [])

    def test_invalid_docx_is_rejected(self):
        upload = AsyncUpload("not-a-docx.docx", b"not a zip archive")

        with self.assertRaises(UploadValidationError):
            asyncio.run(save_and_validate_upload(upload, self.upload_directory))

    def test_oversized_upload_is_rejected(self):
        upload = AsyncUpload("large.txt", b"x" * (MAX_UPLOAD_BYTES + 1))

        with self.assertRaises(UploadValidationError) as error:
            asyncio.run(save_and_validate_upload(upload, self.upload_directory))

        self.assertEqual(error.exception.status_code, 413)

    def test_content_hash_is_unique_within_one_chat_only(self):
        first_chat_id = database.create_chat("First chat")
        second_chat_id = database.create_chat("Second chat")
        content_hash = "a" * 64

        database.create_document(
            first_chat_id,
            "first.txt",
            "first-safe.txt",
            10,
            content_hash,
        )

        self.assertIsNotNone(database.get_document_by_hash(first_chat_id, content_hash))

        with self.assertRaises(sqlite3.IntegrityError):
            database.create_document(
                first_chat_id,
                "duplicate.txt",
                "duplicate-safe.txt",
                10,
                content_hash,
            )

        database.create_document(
            second_chat_id,
            "second.txt",
            "second-safe.txt",
            10,
            content_hash,
        )
        self.assertIsNotNone(database.get_document_by_hash(second_chat_id, content_hash))

    def test_rag_metadata_and_search_filter_are_chat_specific(self):
        collection = FakeCollection()
        fake_ollama = types.SimpleNamespace(
            embed=lambda model, input: {"embeddings": [[0.1] for _ in input]}
        )
        fake_chromadb = types.SimpleNamespace(
            PersistentClient=lambda path: FakeChromaClient(collection)
        )
        original_rag = sys.modules.pop("backend.rag", None)

        try:
            with mock.patch.dict(
                sys.modules,
                {"ollama": fake_ollama, "chromadb": fake_chromadb},
            ):
                rag = importlib.import_module("backend.rag")
                text_path = Path(self.temporary_directory.name) / "chat-two.txt"
                text_path.write_text("Chat two private document text.", encoding="utf-8")

                result = rag.index_document(text_path, "chat-two.txt", 2, 9)
                sources = rag.search_documents("private", 2)

            self.assertEqual(result["chunks"], 1)
            self.assertEqual(collection.add_calls[0]["metadatas"][0]["chat_id"], 2)
            self.assertEqual(collection.add_calls[0]["metadatas"][0]["document_id"], 9)
            self.assertEqual(collection.query_calls[0]["where"], {"chat_id": 2})
            self.assertEqual(sources[0]["document_id"], 9)
        finally:
            sys.modules.pop("backend.rag", None)
            if original_rag is not None:
                sys.modules["backend.rag"] = original_rag


if __name__ == "__main__":
    unittest.main()
