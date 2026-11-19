import {useState, type FormEvent} from "react";
import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {useNavigate} from "react-router-dom";
import {FileText, Search, Trash2, Upload} from "lucide-react";
import {Button} from "../components/ui/button";
import {api, json, type Source} from "../services/api";
import {useSession, type User} from "../store/session";
import type {Conversation, DocumentItem, Model} from "./Chat";

export function Documents() {
  const cache = useQueryClient();
  const navigate = useNavigate();
  const [results, setResults] = useState<(Source & {text: string})[] | null>(null);
  const documents = useQuery({queryKey: ["documents"], queryFn: () => api<DocumentItem[]>("/documents"),
    refetchInterval: query => query.state.data?.some(item => item.processing_status === "queued") ? 2000 : false});
  const upload = useMutation({mutationFn: (body: FormData) => api("/documents/upload", {method: "POST", body}),
    onSuccess: () => cache.invalidateQueries({queryKey: ["documents"]})});
  const remove = useMutation({mutationFn: (id: string) => api("/documents/" + id, {method: "DELETE"}),
    onSuccess: async () => { setResults(null); await cache.invalidateQueries({queryKey: ["documents"]}); }});
  const search = useMutation({mutationFn: (value: string) => api<(Source & {text: string})[]>("/documents/search",
    json("POST", {query: value})), onSuccess: setResults});
  const chat = useMutation({mutationFn: (item: DocumentItem) => api<Conversation>("/conversations",
    json("POST", {document_id: item.id, title: item.filename})), onSuccess: async item => {
      await cache.invalidateQueries({queryKey: ["conversations"]});
      navigate("/chat/" + item.id);
    }});
  const error = [documents.error, upload.error, remove.error, search.error, chat.error].find(Boolean);
  return <section className="workspace">
    <h1>Documents</h1>
    <div className="panel stack">
      <form className="row" onSubmit={event => {
        event.preventDefault();
        const form = event.currentTarget;
        upload.mutate(new FormData(form), {onSuccess: () => form.reset()});
      }}>
        <input type="file" name="file" aria-label="Document file" accept=".pdf,.docx,.txt,.md,.markdown" required/>
        <Button type="submit" variant="primary" disabled={upload.isPending}><Upload size={16}/> Upload</Button>
      </form>
      <form className="row" onSubmit={event => {
        event.preventDefault();
        search.mutate(String(new FormData(event.currentTarget).get("query")));
      }}>
        <input name="query" aria-label="Document search query" placeholder="Search document content" required maxLength={2000}/>
        <Button type="submit" disabled={search.isPending}><Search size={16}/> Search</Button>
      </form>
    </div>
    {error && <p role="alert" className="error">{error.message}</p>}
    {results && <div className="panel stack"><h2>Search results</h2>
      {!results.length && <p>No results found.</p>}
      {results.map(item => <article key={item.document_id + ":" + item.chunk}>
        <strong>{item.filename} · Chunk {item.chunk}</strong><p>{item.text}</p>
      </article>)}</div>}
    <div className="panel stack">
      {documents.isPending && <p role="status">Loading documents…</p>}
      {documents.data?.length === 0 && <p className="muted">No documents uploaded.</p>}
      {documents.data?.map(item => <div className="data-row" key={item.id}>
        <FileText size={19}/><div className="grow"><strong>{item.filename}</strong><div className="muted">{item.processing_status}</div></div>
        <Button disabled={item.processing_status !== "ready" || chat.isPending} onClick={() => chat.mutate(item)}>Chat</Button>
        <Button variant="ghost" aria-label={"Delete " + item.filename} disabled={remove.isPending} onClick={() => {
          if (window.confirm("Delete " + item.filename + "?")) remove.mutate(item.id);
        }}><Trash2 size={16}/></Button>
      </div>)}
    </div>
  </section>;
}

type Execution = {id: string; agent_name: string; execution_status: string; created_at: string;
  execution_metadata: {duration_seconds?: number; model?: string; token_usage?: Record<string, unknown>; error?: string}};

export function Executions() {
  const [id, setId] = useState("");
  const history = useQuery({queryKey: ["executions"], queryFn: () => api<Execution[]>("/agents/executions"),
    refetchInterval: query => query.state.data?.some(item => item.execution_status === "running") ? 3000 : false});
  const details = useQuery({queryKey: ["execution", id], enabled: !!id,
    queryFn: () => api<{execution: Execution; tools: {id: string; tool_name: string; status: string;
      execution_time: number}[]}>("/agents/executions/" + id),
    refetchInterval: query => query.state.data?.execution.execution_status === "running" ? 3000 : false});
  return <section className="workspace"><h1>Agent executions</h1>
    {(history.error || details.error) && <p role="alert" className="error">{history.error?.message || details.error?.message}</p>}
    {history.isPending && <p role="status">Loading executions…</p>}
    <div className="panel stack">
      {history.data?.length === 0 && <p className="muted">No executions yet.</p>}
      {history.data?.map(item => <div className="data-row" key={item.id}>
        <div className="grow"><strong>{item.agent_name}</strong><div className="muted">
          {new Date(item.created_at).toLocaleString()} · {item.execution_status}
          {item.execution_metadata.duration_seconds !== undefined && " · " + item.execution_metadata.duration_seconds + "s"}</div></div>
        <Button aria-expanded={id === item.id} onClick={() => setId(id === item.id ? "" : item.id)}>Details</Button>
      </div>)}
    </div>
    {details.data && <div className="panel stack"><h2>Execution details</h2>
      <p>{details.data.execution.execution_metadata.model}</p>
      {details.data.execution.execution_metadata.error && <p className="error">{details.data.execution.execution_metadata.error}</p>}
      {Object.entries(details.data.execution.execution_metadata.token_usage || {}).filter(([, value]) => typeof value === "number")
        .map(([key, value]) => <p key={key}>{key.replaceAll("_", " ")} · {String(value)}</p>)}
      {details.data.tools.map(tool => <div className="data-row" key={tool.id}>
        {tool.tool_name} · {tool.status} · {tool.execution_time.toFixed(2)}s
      </div>)}
      {!details.data.tools.length && <p className="muted">No tool calls recorded.</p>}
    </div>}
  </section>;
}

export function Settings() {
  const user = useSession(state => state.user)!;
  const setUser = useSession(state => state.setUser);
  const models = useQuery({queryKey: ["models"], queryFn: () => api<Model[]>("/models"), retry: false});
  const save = useMutation({mutationFn: (data: unknown) => api<User>("/auth/me", json("PATCH", data)), onSuccess: setUser});
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate(Object.fromEntries(new FormData(event.currentTarget)));
  }
  return <section className="workspace"><h1>Settings</h1>
    <form className="panel stack settings" onSubmit={submit}>
      <label>Full name<input name="full_name" defaultValue={user.full_name} maxLength={100} required/></label>
      <label>Email<input value={user.email} readOnly/></label>
      <label>Theme<select name="theme" defaultValue={user.preferences.theme || "light"}>
        <option value="light">Light</option><option value="dark">Dark</option>
      </select></label>
      <label>Default model<select name="model" defaultValue={user.preferences.model || ""}>
        <option value="">Server default</option>
        {user.preferences.model && !models.data?.some(item => item.id === user.preferences.model) &&
          <option>{user.preferences.model}</option>}
        {models.data?.map(item => <option key={item.id}>{item.id}</option>)}
      </select></label>
      {save.error && <p role="alert" className="error">{save.error.message}</p>}
      {save.isSuccess && <p role="status">Settings saved.</p>}
      <Button type="submit" variant="primary" disabled={save.isPending}>Save settings</Button>
    </form>
  </section>;
}
