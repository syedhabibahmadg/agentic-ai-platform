from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.v1.auth import Actor, DB
from app.models import Conversation, Document, Message

router = APIRouter(prefix="/conversations", tags=["Conversations"])


class ConversationInput(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=160)
    document_id: str | None = Field(default=None, min_length=1, max_length=36)


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=160)


async def owned(db, user_id: str, identifier: str, lock: bool = False):
    query = select(Conversation).where(Conversation.id == identifier, Conversation.user_id == user_id)
    item = await db.scalar(query.with_for_update() if lock else query)
    if item is None:
        raise HTTPException(404, "Conversation not found")
    return item


@router.post("", status_code=201)
async def create(data: ConversationInput, db: DB, user: Actor):
    if data.document_id:
        document = await db.scalar(select(Document.id).where(
            Document.id == data.document_id, Document.user_id == user.id,
            Document.processing_status == "ready",
        ))
        if not document:
            raise HTTPException(404, "Ready document not found")
    item = Conversation(**data.model_dump(), user_id=user.id)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("")
async def listing(db: DB, user: Actor):
    return list(await db.scalars(select(Conversation).where(
        Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).limit(200)))


@router.get("/{identifier}")
async def detail(identifier: str, db: DB, user: Actor):
    return await owned(db, user.id, identifier)


@router.patch("/{identifier}")
async def rename(identifier: str, data: Rename, db: DB, user: Actor):
    item = await owned(db, user.id, identifier, lock=True)
    item.title = data.title
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{identifier}", status_code=204)
async def delete(identifier: str, request: Request, db: DB, user: Actor):
    if not await db.scalar(select(func.pg_try_advisory_xact_lock(func.hashtextextended(identifier, 0)))):
        raise HTTPException(409, "Stop generation before deleting this conversation")
    item = await owned(db, user.id, identifier, lock=True)
    await db.delete(item)
    await db.commit()
    await request.app.state.checkpointer.adelete_thread(f"{user.id}:{identifier}")


@router.get("/{identifier}/messages")
async def messages(identifier: str, db: DB, user: Actor, limit: int = 100, before: str | None = None):
    await owned(db, user.id, identifier)
    query = select(Message).where(Message.conversation_id == identifier)
    if before:
        anchor = await db.get(Message, before)
        if not anchor or anchor.conversation_id != identifier:
            raise HTTPException(404, "Message not found")
        from sqlalchemy import tuple_
        query = query.where(tuple_(Message.created_at, Message.id) < (anchor.created_at, anchor.id))
    result = await db.scalars(query.order_by(Message.created_at.desc(), Message.id.desc())
                              .limit(max(1, min(200, limit))))
    return list(reversed(result.all()))
