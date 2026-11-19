import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://assistant:password@localhost:5432/assistant")
os.environ.setdefault("JWT_SECRET_KEY", "testing-only-signing-secret-for-local-pytest")
