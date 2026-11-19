from alembic import op

revision = "001_initial"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""CREATE TABLE users (
        id varchar PRIMARY KEY, full_name varchar NOT NULL, email varchar NOT NULL UNIQUE,
        password_hash varchar NOT NULL, role varchar NOT NULL, preferences json NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE documents (
        id varchar PRIMARY KEY, user_id varchar NOT NULL REFERENCES users ON DELETE CASCADE,
        filename varchar NOT NULL, file_type varchar NOT NULL, processing_status varchar NOT NULL,
        upload_data bytea, attempts integer NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE conversations (
        id varchar PRIMARY KEY, user_id varchar NOT NULL REFERENCES users ON DELETE CASCADE,
        document_id varchar REFERENCES documents ON DELETE SET NULL, title varchar NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE messages (
        id varchar PRIMARY KEY, conversation_id varchar NOT NULL REFERENCES conversations ON DELETE CASCADE,
        role varchar NOT NULL, content text NOT NULL, model_name varchar, token_usage json,
        sources json NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE document_chunks (
        id varchar PRIMARY KEY, document_id varchar NOT NULL REFERENCES documents ON DELETE CASCADE,
        chunk_index integer NOT NULL, content text NOT NULL, embedding vector(384) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(document_id, chunk_index))""")
    op.execute("""CREATE TABLE agent_executions (
        id varchar PRIMARY KEY, user_id varchar NOT NULL REFERENCES users ON DELETE CASCADE,
        conversation_id varchar NOT NULL REFERENCES conversations ON DELETE CASCADE,
        agent_name varchar NOT NULL, execution_status varchar NOT NULL, execution_metadata json NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE tool_calls (
        id varchar PRIMARY KEY, execution_id varchar NOT NULL REFERENCES agent_executions ON DELETE CASCADE,
        tool_name varchar NOT NULL, input_data json NOT NULL, output_data json NOT NULL,
        execution_time double precision NOT NULL, status varchar NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE refresh_tokens (
        id varchar PRIMARY KEY, user_id varchar NOT NULL REFERENCES users ON DELETE CASCADE,
        token_hash varchar NOT NULL UNIQUE, expires_at timestamptz NOT NULL, revoked_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now())""")
    for table, columns in {
        "documents": ("user_id", "processing_status"), "conversations": ("user_id", "document_id"),
        "messages": ("conversation_id",), "agent_executions": ("user_id", "conversation_id"),
        "tool_calls": ("execution_id",), "refresh_tokens": ("user_id",),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index("ix_messages_history", "messages", ["conversation_id", "created_at", "id"])


def downgrade():
    for table in ["refresh_tokens", "tool_calls", "agent_executions", "document_chunks",
                  "messages", "conversations", "documents", "users"]:
        op.drop_table(table)
