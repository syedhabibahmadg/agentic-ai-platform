import asyncio
import io
import re
import unicodedata
import zipfile
from functools import lru_cache

from docx import Document as WordDocument
from fastembed import TextEmbedding
from pypdf import PdfReader
from sqlalchemy import select

from app.db.session import Session
from app.models import Document, DocumentChunk


@lru_cache
def embedding_model():
    return TextEmbedding("BAAI/bge-small-en-v1.5", threads=2)


def extract(data: bytes, extension: str) -> list[str]:
    stream = io.BytesIO(data)
    if extension == ".pdf":
        reader = PdfReader(stream)
        if reader.is_encrypted or len(reader.pages) > 300:
            raise ValueError("Encrypted or oversized PDF")
        raw = "\n".join(page.extract_text() for page in reader.pages)
    elif extension == ".docx":
        with zipfile.ZipFile(stream) as archive:
            if sum(item.file_size for item in archive.infolist()) > 40_000_000:
                raise ValueError("Oversized document")
        stream.seek(0)
        word = WordDocument(stream)
        raw = "\n".join([p.text for p in word.paragraphs] + [
            cell.text for table in word.tables for row in table.rows for cell in row.cells
        ])
    else:
        raw = data.decode("utf-8-sig")
        if "\x00" in raw:
            raise ValueError("Invalid text file")
    content = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw)).strip()
    if not content or len(content) > 1_000_000:
        raise ValueError("Document has no extractable text or exceeds the text limit")
    return [content[start:start + 1000] for start in range(0, len(content), 850)]


def build_chunks(data: bytes, extension: str):
    chunks = extract(data, extension)
    return list(zip(chunks, embedding_model().passage_embed(chunks), strict=True))


def query_vector(query: str):
    return next(iter(embedding_model().query_embed(query))).tolist()


async def search(user_id: str, query: str, document_id: str | None = None, limit: int = 5):
    async with Session() as db:
        scope = [Document.user_id == user_id, Document.processing_status == "ready"]
        if document_id:
            scope.append(Document.id == document_id)
        if not await db.scalar(select(Document.id).where(*scope).limit(1)):
            return []
        vector = await asyncio.to_thread(query_vector, query)
        distance = DocumentChunk.embedding.cosine_distance(vector)
        rows = await db.execute(select(DocumentChunk, Document.filename, distance.label("distance"))
                                .join(Document).where(*scope).order_by(distance).limit(limit))
        return [{"document_id": chunk.document_id, "filename": filename,
                 "chunk": chunk.chunk_index + 1, "text": chunk.content, "distance": score}
                for chunk, filename, score in rows]


async def process_one() -> bool:
    async with Session.begin() as db:
        document = await db.scalar(select(Document).where(Document.processing_status == "queued")
                                   .order_by(Document.created_at).limit(1).with_for_update(skip_locked=True))
        if document is None:
            return False
        try:
            chunks = await asyncio.to_thread(build_chunks, document.upload_data, document.file_type)
        except ValueError:
            document.processing_status = "failed"
        except Exception:
            document.attempts += 1
            document.processing_status = "failed" if document.attempts >= 3 else "queued"
        else:
            db.add_all(DocumentChunk(document_id=document.id, chunk_index=index,
                                     content=content, embedding=vector.tolist())
                       for index, (content, vector) in enumerate(chunks))
            document.processing_status = "ready"
        if document.processing_status != "queued":
            document.upload_data = None
        return True
