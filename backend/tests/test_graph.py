import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agents import graph
from app.agents.tools import calculator
from app.rag.retriever import extract


def test_calculator_and_text():
    assert calculator.invoke({"expression": "2 * (3 + 4)"}) == {"result": 14}
    with pytest.raises(ValueError):
        calculator.invoke({"expression": "open('secret')"})
    assert extract(b"hello\nworld", ".txt") == ["hello world"]
    with pytest.raises(ValueError):
        extract(b"\x00", ".md")


class Model:
    route = "conversation"

    async def ainvoke(self, messages, config=None):
        return AIMessage(content=self.route)

    async def astream(self, messages):
        yield AIMessageChunk(content="Hello")
        yield AIMessageChunk(content=" world")


@pytest.mark.asyncio
@pytest.mark.parametrize("document", [None, "document-1"])
async def test_graph_routes_and_streams(monkeypatch, document):
    monkeypatch.setattr(graph, "make_model", lambda _: Model())

    async def search(user_id, query, document_id):
        assert (user_id, query, document_id) == ("owner", "hello", document)
        return [{"filename": "example.txt", "chunk": 1, "text": "hello"}]

    monkeypatch.setattr(graph, "search", search)
    app = graph.compile_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "owner:thread"}}
    events = [event async for event in app.astream({
        "history": [HumanMessage(content="hello")], "model": "test", "user_id": "owner",
        "document_id": document, "execution_id": "execution",
    }, config=config, stream_mode="custom")]
    assert events == [{"type": "delta", "text": "Hello"}, {"type": "delta", "text": " world"}]
    saved = (await app.aget_state(config)).values
    assert saved["intent"] == ("documents" if document else "conversation")
    assert saved["answer"] == "Hello world"


@pytest.mark.asyncio
async def test_graph_sanitizes_provider_errors(monkeypatch):
    class Broken(Model):
        async def astream(self, messages):
            raise RuntimeError("provider secret")
            yield

    monkeypatch.setattr(graph, "make_model", lambda _: Broken())
    app = graph.compile_graph(InMemorySaver())
    events = [event async for event in app.astream({
        "history": [HumanMessage(content="hello")], "model": "test", "user_id": "owner",
        "document_id": None, "execution_id": "execution",
    }, config={"configurable": {"thread_id": "error"}}, stream_mode="custom")]
    assert len(events) == 1 and events[0]["type"] == "error"
    assert "secret" not in str(events)
