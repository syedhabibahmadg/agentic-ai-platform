import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, JSON, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Updated:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Record, Updated, Base):
    __tablename__ = "users"
    full_name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    role: Mapped[str] = mapped_column(default="user")
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)


class Document(Record, Base):
    __tablename__ = "documents"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str]
    file_type: Mapped[str]
    processing_status: Mapped[str] = mapped_column(index=True, default="queued")
    upload_data: Mapped[bytes | None]
    attempts: Mapped[int] = mapped_column(default=0)


class Conversation(Record, Updated, Base):
    __tablename__ = "conversations"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(default="New conversation")


class Message(Record, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str | None]
    token_usage: Mapped[dict | None] = mapped_column(JSON)
    sources: Mapped[list] = mapped_column(JSON, default=list)


class DocumentChunk(Record, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index"),)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(Vector(384))


class AgentExecution(Record, Base):
    __tablename__ = "agent_executions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    agent_name: Mapped[str] = mapped_column(default="assistant")
    execution_status: Mapped[str]
    execution_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class ToolCall(Record, Base):
    __tablename__ = "tool_calls"
    execution_id: Mapped[str] = mapped_column(ForeignKey("agent_executions.id", ondelete="CASCADE"), index=True)
    tool_name: Mapped[str]
    input_data: Mapped[dict] = mapped_column(JSON)
    output_data: Mapped[dict] = mapped_column(JSON)
    execution_time: Mapped[float]
    status: Mapped[str]


class RefreshToken(Record, Base):
    __tablename__ = "refresh_tokens"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
