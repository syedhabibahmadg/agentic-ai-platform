import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from sqlalchemy import text

from app.agents.graph import compile_graph
from app.api.v1 import agents, auth, chat, conversations, documents
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import engine, postgres_dsn
from app.rag.retriever import process_one

configure_logging()
logger = logging.getLogger(__name__)


async def worker():
    while True:
        try:
            if await process_one():
                continue
        except Exception:
            logger.exception("Document worker iteration failed")
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app):
    async with Redis.from_url(settings().redis_url, socket_timeout=5) as redis:
        app.state.redis = redis
        async with AsyncPostgresSaver.from_conn_string(postgres_dsn()) as saver:
            app.state.checkpointer = saver
            app.state.graph = compile_graph(saver)
            task = asyncio.create_task(worker())
            try:
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
    await engine.dispose()


app = FastAPI(title=settings().app_name, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origins.split(","),
                   allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["Content-Type", "Authorization"])
for router in (auth.router, conversations.router, chat.router, documents.router, agents.router):
    app.include_router(router, prefix="/api/v1")


@app.exception_handler(RequestValidationError)
async def invalid_input(request: Request, error: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": [
        {key: item[key] for key in ("type", "loc", "msg")} for item in error.errors()
    ]})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready(request: Request):
    try:
        await request.app.state.redis.ping()
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1 FROM users LIMIT 1"))
            await connection.execute(text("SELECT 1 FROM checkpoints LIMIT 1"))
    except Exception as exc:
        raise HTTPException(503, "Dependencies unavailable") from exc
    return {"status": "ready"}
