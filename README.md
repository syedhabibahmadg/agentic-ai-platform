# Agentic AI Platform

A private multi-user assistant built with React, FastAPI, LangGraph, Groq, PostgreSQL with pgvector, and Redis. The browser uses same-origin API requests. FastAPI owns authorization and transport, and the LangGraph pipeline routes each turn to conversation, document retrieval, research, or a bounded tool loop. PostgreSQL stores the application records and LangGraph checkpoints. Redis provides rate limits and caches the Groq model list.

## Quick start

Install Docker with Compose and obtain a Groq API key. Copy `.env.example` to `.env` and set `GROQ_API_KEY`, `JWT_SECRET_KEY`, and `POSTGRES_PASSWORD`. Use a URL-safe database password for Compose's connection URI. Generate the JWT secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

```sh
docker compose up --build -d
docker compose ps
docker compose logs -f migrate backend
```

Open [the application](http://localhost:8080), register, and start a chat. [Swagger](http://localhost:8080/docs) is available through the same origin. Upload PDF, DOCX, UTF-8 text, or Markdown in Documents. Once the status is ready, search the file or choose Chat next to it. The first upload downloads the BGE embedding model into the persistent embedding cache. Scanned PDFs need a text layer.

The `migrate` service installs pgvector, runs Alembic, and runs the official LangGraph checkpoint migrations before the API starts. PostgreSQL and Redis are internal to Compose. Application records survive container replacement when the named volume is retained.

## Development

Use Node 22 and Python 3.11 or newer. The checkpoint driver uses psycopg's async client. Run the backend in Docker, Linux, or WSL when developing on Windows.

```sh
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.db.checkpoints
uvicorn app.main:app --reload
```

Local backend development needs reachable PostgreSQL with pgvector and Redis instances. Set the connection URLs accordingly in the root `.env`.

```sh
cd frontend
npm install
npm run dev
npm test
npm run build
```

Vite proxies API calls to port 8000. For a frontend using the Compose API, use the frontend image or point Vite's proxy at port 8080.

## Automated checks

```sh
docker compose run --rm backend python -m pytest -q -p no:cacheprovider
docker compose run --rm -e RUN_INTEGRATION=1 backend python -m pytest -q -p no:cacheprovider
```

Run integration tests on a disposable development database. They create accounts and use real PostgreSQL, Redis, routing, checkpointing, and ASGI requests. LLM replies and embeddings are substituted in the suite. To verify the real provider path, start Compose with a valid Groq key, send a message, upload a text document, wait for Ready, and ask a question in its document chat. Confirm streamed text, citations, and the execution record. Sign in as a second user to check that the first account's conversations and documents are absent.

## Deployment

Build the two images in CI, run the migration job once before deploying new API replicas, and put the frontend behind a TLS reverse proxy. Configure `APP_ENV=production` for Secure cookies, exact `CORS_ORIGINS`, an HTTPS `PUBLIC_APP_URL`, and secret-backed credentials. Use a same-origin reverse proxy with request body limits and SSE buffering disabled. Restrict database and Redis access to application networks and back up PostgreSQL. Set `GROQ_MODELS` to the permitted Groq IDs and `GROQ_TOOL_MODELS` to the provider-documented tool-capable subset. The API intersects its configuration with Groq's live model list. `BRAVE_API_KEY` enables the optional public web search tool.

Uploads are queued in PostgreSQL and processed with row locking. Source text and vectors remain in PostgreSQL. Retrieved excerpts and recent conversation messages are sent to Groq as model context. The website serves no provider keys. Configure retention and backups for application data and LangGraph checkpoints according to your deployment requirements.

Password reset uses a STARTTLS SMTP server. Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `RESET_SENDER`, and `PUBLIC_APP_URL`. Reset links expire after 30 minutes and are single-use. A successful reset revokes existing refresh tokens.

- Groq local tool support is documented in [GroqDocs](https://console.groq.com/docs/tool-use/overview).
- API routes and types are listed in FastAPI's generated OpenAPI schema.
