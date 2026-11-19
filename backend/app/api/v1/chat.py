import asyncio
import json
import logging
from time import monotonic
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.v1.auth import Actor, rate
from app.api.v1.conversations import owned
from app.core.config import settings
from app.db.session import Session
from app.models import AgentExecution, Message

router = APIRouter(tags=["Chat"])
logger = logging.getLogger(__name__)


class ChatInput(BaseModel):
    conversation_id: str = Field(max_length=36)
    content: str = Field(default="", max_length=12000)
    model: str | None = Field(default=None, max_length=150)
    action: Literal["message", "regenerate"] = "message"


@router.get("/models")
async def models(request: Request, user: Actor):
    config = settings()
    configured = set(config.groq_models.split(","))
    cache = request.app.state.redis
    try:
        available = await cache.get("groq:models")
        if available is None:
            if not config.groq_api_key:
                raise HTTPException(503, "Groq requires a server API key")
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get("https://api.groq.com/openai/v1/models",
                                            headers={"Authorization": f"Bearer {config.groq_api_key}"})
                response.raise_for_status()
                available = json.dumps([item["id"] for item in response.json()["data"]])
            await cache.set("groq:models", available, ex=300)
        configured.intersection_update(json.loads(available))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(503, "Model availability could not be verified") from exc
    return [{"id": name, "tools": name in config.groq_tool_models.split(",")} for name in sorted(configured)]


async def validate(data: ChatInput, request: Request, user: Actor):
    await rate(request, f"chat:{user.id}", 20)
    if data.action == "message" and not data.content.strip():
        raise HTTPException(422, "Enter a message")
    async with Session() as db:
        await owned(db, user.id, data.conversation_id)
    available = {item["id"] for item in await models(request, user)}
    model = data.model or user.preferences.get("model") or settings().groq_models.split(",")[0]
    if model not in available:
        raise HTTPException(422, "Selected model is unavailable")
    return model


async def events(request, user_id, data, model):
    execution_id = None
    started = monotonic()
    status = "failed"
    result = {}
    try:
        async with Session.begin() as guard:
            locked = await guard.scalar(select(func.pg_try_advisory_xact_lock(
                func.hashtextextended(data.conversation_id, 0))))
            if not locked:
                yield {"type": "error", "message": "A response is already running"}
                return
            async with Session.begin() as db:
                conversation = await owned(db, user_id, data.conversation_id)
                identifier, document_id = conversation.id, conversation.document_id
                rows = list(reversed((await db.scalars(select(Message).where(
                    Message.conversation_id == identifier).order_by(Message.created_at.desc(),
                    Message.id.desc()).limit(settings().context_messages + 1))).all()))
                replace_id = None
                if data.action == "regenerate":
                    if rows and rows[-1].role == "assistant":
                        replace_id = rows.pop().id
                    if not rows or rows[-1].role != "user":
                        yield {"type": "error", "message": "There is no message to regenerate"}
                        return
                else:
                    rows.append(Message(conversation_id=identifier, role="user", content=data.content.strip()))
                    db.add(rows[-1])
                    if conversation.title == "New conversation":
                        conversation.title = data.content.strip()[:80]
                    conversation.updated_at = func.now()
                execution = AgentExecution(conversation_id=identifier, user_id=user_id,
                                           execution_status="running")
                db.add(execution)
                await db.flush()
                execution_id = execution.id
                history = [HumanMessage(content=row.content) if row.role == "user"
                           else AIMessage(content=row.content) for row in rows[-settings().context_messages:]]

            config = {"configurable": {"thread_id": f"{user_id}:{identifier}"},
                      "recursion_limit": settings().graph_recursion_limit}
            graph = request.app.state.graph
            async with asyncio.timeout(150):
                async for mode, event in graph.astream(
                    {"history": history, "user_id": user_id, "document_id": document_id,
                     "model": model, "execution_id": execution_id}, config=config,
                    stream_mode=["custom", "values"],
                ):
                    if mode == "custom":
                        yield event
                    else:
                        result = event
            if result.get("failed"):
                return
            async with Session.begin() as db:
                item = (await db.get(Message, replace_id)) if replace_id else None
                if item is None:
                    item = Message(conversation_id=identifier, role="assistant")
                    db.add(item)
                item.content, item.model_name = result["answer"], model
                item.token_usage = result.get("usage")
                item.sources = [{k: source[k] for k in ("document_id", "filename", "chunk")}
                                for source in result.get("sources", [])]
                await db.flush()
                done = {"type": "done", "id": item.id, "content": item.content, "sources": item.sources,
                        "token_usage": item.token_usage}
            status = "completed"
            yield done
    except (asyncio.CancelledError, GeneratorExit):
        if status != "completed":
            status = "cancelled"
        raise
    except Exception:
        logger.exception("Chat execution failed (%s)", execution_id)
        yield {"type": "error", "message": "The assistant could not complete this response. Try again."}
    finally:
        if execution_id:
            async def finish():
                async with Session.begin() as db:
                    execution = await db.get(AgentExecution, execution_id)
                    if execution:
                        execution.execution_status = status
                        execution.agent_name = result.get("intent", "assistant")
                        execution.execution_metadata = {
                            "duration_seconds": round(monotonic() - started, 3), "model": model,
                            "token_usage": result.get("usage"), "error": (
                                "Agent execution failed" if status == "failed" else None
                            ),
                        }
            await asyncio.shield(finish())


async def stream(data, request, user):
    model = await validate(data, request, user)

    async def frames():
        from contextlib import aclosing
        async with aclosing(events(request, user.id, data, model)) as iterator:
            async for event in iterator:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(frames(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/chat/stream")
async def chat_stream(data: ChatInput, request: Request, user: Actor):
    return await stream(data, request, user)


@router.post("/chat/regenerate")
async def regenerate(data: ChatInput, request: Request, user: Actor):
    return await stream(data.model_copy(update={"action": "regenerate"}), request, user)


@router.post("/chat")
async def chat(data: ChatInput, request: Request, user: Actor):
    model = await validate(data, request, user)
    from contextlib import aclosing
    async with aclosing(events(request, user.id, data, model)) as iterator:
        async for event in iterator:
            if event["type"] == "done":
                result = event
            elif event["type"] == "error":
                raise HTTPException(502, event["message"])
    return result
