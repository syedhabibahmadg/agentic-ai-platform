import json
import os
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from app.agents import graph
from app.main import app

pytestmark = pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="Requires migrated PostgreSQL and Redis")


class MockGroq:
    async def ainvoke(self, messages, config=None):
        return AIMessage(content="conversation")

    async def astream(self, messages):
        yield AIMessageChunk(content="Test response")


@pytest.mark.asyncio
async def test_user_chat_document_and_isolation(monkeypatch):
    monkeypatch.setattr(graph, "make_model", lambda name: MockGroq())
    monkeypatch.setattr("app.rag.retriever.build_chunks", lambda data, extension: [
        (data.decode(), __import__("array").array("f", [1.0] + [0.0] * 383)),
    ])
    monkeypatch.setattr("app.rag.retriever.query_vector", lambda query: [1.0] + [0.0] * 383)
    from app.core.config import settings
    prefix = "/api/v1"
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        await app.state.redis.set("groq:models", json.dumps(settings().groq_models.split(",")), ex=10)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert (await client.get(prefix + "/conversations")).status_code == 401
            accounts = []
            for position in range(2):
                profile = {"full_name": f"Test {position}", "email": f"{uuid4()}@example.com",
                           "password": "a-good-test-password"}
                response = await client.post(prefix + "/auth/register", json=profile)
                assert response.status_code == 201
                accounts.append({"Authorization": "Bearer " + response.json()["access_token"]})
            response = await client.post(prefix + "/auth/login", json=profile)
            assert response.status_code == 200
            old_cookie = client.cookies.get("assistant_refresh")
            assert (await client.post(prefix + "/auth/refresh")).status_code == 200
            assert old_cookie != client.cookies.get("assistant_refresh")
            owner, other = accounts
            response = await client.post(prefix + "/conversations", json={}, headers=owner)
            assert response.status_code == 201
            identifier = response.json()["id"]
            url = prefix + "/conversations/" + identifier
            assert (await client.get(url, headers=other)).status_code == 404
            response = await client.post(prefix + "/chat/stream", headers=owner,
                                         json={"conversation_id": identifier, "content": "hello"})
            assert response.status_code == 200
            assert "Test response" in response.text and '"type": "done"' in response.text
            history = await client.get(url + "/messages", headers=owner)
            assert [message["content"] for message in history.json()] == ["hello", "Test response"]
            response = await client.post(prefix + "/documents/upload", headers=owner,
                                         files={"file": ("notes.txt", b"Private text", "text/plain")})
            assert response.status_code == 202
            document_id = response.json()["id"]
            assert (await client.get(prefix + "/documents/" + document_id, headers=other)).status_code == 404
            import asyncio
            for attempt in range(25):
                document = await client.get(prefix + "/documents/" + document_id, headers=owner)
                if document.json()["processing_status"] == "ready":
                    break
                await asyncio.sleep(0.2)
            query = {"query": "private"}
            response = await client.post(prefix + "/documents/search", headers=owner, json=query)
            assert response.json()[0]["text"] == "Private text"
            response = await client.post(prefix + "/documents/search", headers=other, json=query)
            assert response.json() == []
            await client.delete(prefix + "/documents/" + document_id, headers=owner)
            await client.delete(url, headers=owner)
            await client.post(prefix + "/auth/logout")
