from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.v1.auth import Actor, DB
from app.models import AgentExecution, ToolCall

router = APIRouter(prefix="/agents", tags=["Monitoring"])


@router.get("")
async def agents(user: Actor):
    return [{"name": "conversation"}, {"name": "documents"}, {"name": "research"}, {"name": "tools"}]


@router.get("/executions")
async def executions(db: DB, user: Actor):
    return list(await db.scalars(select(AgentExecution).where(AgentExecution.user_id == user.id)
                                 .order_by(AgentExecution.created_at.desc()).limit(100)))


@router.get("/executions/{identifier}")
async def execution(identifier: str, db: DB, user: Actor):
    item = await db.scalar(select(AgentExecution).where(
        AgentExecution.id == identifier, AgentExecution.user_id == user.id))
    if item is None:
        raise HTTPException(404, "Execution not found")
    calls = await db.scalars(select(ToolCall).where(ToolCall.execution_id == item.id)
                             .order_by(ToolCall.created_at))
    return {"execution": item, "tools": calls.all()}


@router.get("/admin/status")
async def admin_status(db: DB, user: Actor):
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    rows = await db.execute(select(AgentExecution.execution_status, func.count())
                            .group_by(AgentExecution.execution_status))
    return {"executions_by_status": dict(rows.all())}
