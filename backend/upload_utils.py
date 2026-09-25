import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
import uuid
import zipfile

from docx import Document
from pypdf import PdfReader

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
READ_CHUNK_SIZE = 1024 * 1024


class UploadValidationError(ValueError):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class StoredUpload:
    original_filename: str
    stored_filename: str
    file_path: Path
    size_bytes: int
    content_hash: str


def get_safe_original_filename(filename):
    normalized_filename = (filename or "").replace("\\", "/")
    original_filename = normalized_filename.rsplit("/", 1)[-1].strip()

    if not original_filename or original_filename in {".", ".."}:
        raise UploadValidationError("A valid filename is required.", 400)

    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise UploadValidationError("Use a PDF, DOCX, or TXT file.", 415)

    return original_filename, extension


def validate_file_contents(file_path, extension):
    if extension == ".pdf":
        with open(file_path, "rb") as file:
            if file.read(5) != b"%PDF-":
                raise UploadValidationError("The file is not a valid PDF.", 400)

        try:
            len(PdfReader(file_path).pages)
        except Exception as error:
            raise UploadValidationError("The file is not a valid PDF.", 400) from error

    elif extension == ".docx":
        if not zipfile.is_zipfile(file_path):
            raise UploadValidationError("The file is not a valid DOCX document.", 400)

        with zipfile.ZipFile(file_path) as archive:
            names = set(archive.namelist())

        if "[Content_Types].xml" not in names or "word/document.xml" not in names:
            raise UploadValidationError("The file is not a valid DOCX document.", 400)

        try:
            Document(file_path)
        except Exception as error:
            raise UploadValidationError("The file is not a valid DOCX document.", 400) from error

    elif extension == ".txt":
        try:
            text = file_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            raise UploadValidationError("TXT files must use UTF-8 encoding.", 400) from error

        if not text.strip():
            raise UploadValidationError("The text file is empty.", 400)


async def save_and_validate_upload(upload_file, upload_directory):
    original_filename, extension = get_safe_original_filename(upload_file.filename)

    upload_directory = Path(upload_directory)
    upload_directory.mkdir(parents=True, exist_ok=True)

    temporary_path = upload_directory / f".{uuid.uuid4().hex}.uploading"
    stored_filename = f"{uuid.uuid4().hex}{extension}"
    stored_path = upload_directory / stored_filename
    digest = hashlib.sha256()
    size_bytes = 0

    try:
        with open(temporary_path, "wb") as buffer:
            while chunk := await upload_file.read(READ_CHUNK_SIZE):
                size_bytes += len(chunk)

                if size_bytes > MAX_UPLOAD_BYTES:
                    raise UploadValidationError(
                        "Files must be 10 MB or smaller.",
                        413,
                    )

                digest.update(chunk)
                buffer.write(chunk)

        if size_bytes == 0:
            raise UploadValidationError("The uploaded file is empty.", 400)

        validate_file_contents(temporary_path, extension)
        os.replace(temporary_path, stored_path)

        return StoredUpload(
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_path=stored_path,
            size_bytes=size_bytes,
            content_hash=digest.hexdigest(),
        )
    except Exception:
        cleanup_upload(temporary_path)
        cleanup_upload(stored_path)
        raise


def cleanup_upload(file_path):
    Path(file_path).unlink(missing_ok=True)
