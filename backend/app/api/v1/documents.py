from pathlib import PurePosixPath

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import defer

from app.api.v1.auth import Actor, DB, rate
from app.core.config import settings
from app.models import Document
from app.rag.retriever import search

router = APIRouter(prefix="/documents", tags=["Documents"])


def public(document: Document):
    return {key: getattr(document, key) for key in
            ("id", "filename", "file_type", "processing_status", "created_at")}


async def owned(db, user_id: str, identifier: str):
    item = await db.scalar(select(Document).options(defer(Document.upload_data)).where(
        Document.id == identifier, Document.user_id == user_id))
    if item is None:
        raise HTTPException(404, "Document not found")
    return item


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    document_id: str | None = Field(default=None, max_length=36)
    limit: int = Field(default=5, ge=1, le=20)


@router.post("/upload", status_code=202)
async def upload(request: Request, db: DB, user: Actor, file: UploadFile = File()):
    await rate(request, f"upload:{user.id}", 10)
    filename = PurePosixPath((file.filename or "").replace("\\", "/")).name
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in {".pdf", ".docx", ".txt", ".md", ".markdown"} or len(filename) > 255:
        raise HTTPException(415, "Upload a PDF, DOCX, TXT or Markdown file")
    data = await file.read(settings().upload_limit + 1)
    if len(data) > settings().upload_limit:
        raise HTTPException(413, "File exceeds the upload limit")
    if not data or (extension == ".pdf" and not data.startswith(b"%PDF-")) or (
        extension == ".docx" and not data.startswith(b"PK\x03\x04")
    ):
        raise HTTPException(422, "File is empty or its contents do not match its extension")
    item = Document(user_id=user.id, filename=filename, file_type=extension, upload_data=data)
    db.add(item)
    await db.commit()
    return public(item)


@router.get("")
async def listing(db: DB, user: Actor):
    rows = await db.scalars(select(Document).options(defer(Document.upload_data)).where(Document.user_id == user.id).order_by(Document.created_at.desc())
                            .limit(200))
    return [public(item) for item in rows]


@router.post("/search")
async def retrieve(data: SearchInput, request: Request, db: DB, user: Actor):
    await rate(request, f"search:{user.id}", 30)
    if data.document_id:
        await owned(db, user.id, data.document_id)
    return await search(user.id, data.query, data.document_id, data.limit)


@router.get("/{identifier}")
async def detail(identifier: str, db: DB, user: Actor):
    return public(await owned(db, user.id, identifier))


@router.delete("/{identifier}", status_code=204)
async def delete(identifier: str, db: DB, user: Actor):
    await db.delete(await owned(db, user.id, identifier))
    await db.commit()
