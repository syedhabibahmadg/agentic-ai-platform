let access = "";
let refreshing: Promise<boolean> | undefined;
const base = "/api/v1";

export function setAccess(value: string) {
  access = value;
}

export function refresh() {
  refreshing ??= fetch(base + "/auth/refresh", {method: "POST", credentials: "same-origin"})
    .then(async response => {
      if (!response.ok) return false;
      setAccess((await response.json()).access_token);
      return true;
    }).catch(() => false).finally(() => { refreshing = undefined; });
  return refreshing;
}

export async function request(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body && typeof init.body === "string") headers.set("Content-Type", "application/json");
  const used = access;
  if (used) headers.set("Authorization", "Bearer " + used);
  const response = await fetch(base + path, {...init, headers});
  if (response.status === 401 && retry && (access !== used || await refresh())) {
    return request(path, init, false);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(typeof payload.detail === "string" ? payload.detail :
      Array.isArray(payload.detail) ? payload.detail.map((item: {msg: string}) => item.msg).join(". ") :
      "Request failed (" + response.status + ")");
  }
  return response;
}

export async function api<T>(path: string, init?: RequestInit, retry = true): Promise<T> {
  const response = await request(path, init, retry);
  return response.status === 204 ? undefined as T : response.json();
}

export function json(method: string, value: unknown): RequestInit {
  return {method, body: JSON.stringify(value)};
}

export type Source = {document_id: string; filename: string; chunk: number};
type Event = {type: "delta"; text: string} | {type: "tool"; name: string; status: string}
  | {type: "done"; content: string; id: string; sources: Source[]} | {type: "error"; message: string};

export async function streamChat(path: string, payload: unknown, signal: AbortSignal, receive: (event: Event) => void) {
  const response = await request(path, {...json("POST", payload), signal});
  const reader = response.body?.getReader();
  if (!reader) throw new Error("Streaming is unavailable");
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  try {
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        if (frame.startsWith("data: ")) {
          const event = JSON.parse(frame.slice(6)) as Event;
          if (event.type === "error") throw new Error(event.message);
          if (event.type === "done") completed = true;
          receive(event);
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
    if (!completed) throw new Error("The response stream closed unexpectedly");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
