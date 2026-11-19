import {afterEach, expect, it, vi} from "vitest";
import {streamChat} from "./api";

afterEach(() => vi.unstubAllGlobals());

it("reassembles fragmented SSE frames and handles the final message", async () => {
  const encoder = new TextEncoder();
  const body = new ReadableStream({start(controller) {
    controller.enqueue(encoder.encode('data: {"type":"delta","text":"Hel'));
    controller.enqueue(encoder.encode('lo"}\n\ndata: {"type":"done","content":"Hello","id":"1","sources":[]}\n\n'));
    controller.close();
  }});
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
  const receive = vi.fn();
  await streamChat("/chat/stream", {}, new AbortController().signal, receive);
  expect(receive).toHaveBeenCalledTimes(2);
  expect(receive).toHaveBeenLastCalledWith({type: "done", content: "Hello", id: "1", sources: []});
});

it("reports an incomplete stream", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("data: {}\n\n")));
  await expect(streamChat("/chat/stream", {}, new AbortController().signal, vi.fn()))
    .rejects.toThrow("closed unexpectedly");
});
