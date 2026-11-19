import {useEffect, useRef, useState, type FormEvent} from "react";
import {useQuery, useQueryClient} from "@tanstack/react-query";
import {useNavigate, useParams} from "react-router-dom";
import {ArrowUp, FileText, RotateCcw, Sparkles, Square} from "lucide-react";
import {Button} from "../components/ui/button";
import {Message, type ChatMessage} from "../components/Message";
import {api, json, streamChat} from "../services/api";
import {useSession} from "../store/session";

export type Conversation = {id: string; title: string; document_id: string | null};
export type Model = {id: string; tools: boolean};
export type DocumentItem = {id: string; filename: string; processing_status: string; created_at: string};

export function Chat() {
  const {id} = useParams();
  const navigate = useNavigate();
  const cache = useQueryClient();
  const preferred = useSession(state => state.user?.preferences.model);
  const [model, setModel] = useState("");
  const [document, setDocument] = useState("");
  const [text, setText] = useState("");
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState("");
  const [tool, setTool] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const previous = useRef(id);
  const messages = useQuery({queryKey: ["messages", id], enabled: !!id,
    queryFn: () => api<ChatMessage[]>("/conversations/" + id + "/messages")});
  const lastMessage = messages.data?.at(-1);
  const models = useQuery({queryKey: ["models"], queryFn: () => api<Model[]>("/models"), retry: false});
  const documents = useQuery({queryKey: ["documents"], queryFn: () => api<DocumentItem[]>("/documents")});
  const conversations = useQuery({queryKey: ["conversations"], queryFn: () => api<Conversation[]>("/conversations")});
  const currentDocument = documents.data?.find(item => item.id ===
    conversations.data?.find(conversation => conversation.id === id)?.document_id);
  const selected = model || models.data?.find(item => item.id === preferred)?.id || models.data?.[0]?.id || "";
  useEffect(() => {
    if (previous.current && previous.current !== id) controller.current?.abort();
    previous.current = id;
  }, [id]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => { end.current?.scrollIntoView({block: "end"}); }, [messages.data, draft, busy]);

  async function send(event?: FormEvent, regenerate = false) {
    event?.preventDefault();
    if (controller.current || !selected || (!regenerate && !text.trim())) return;
    const abort = new AbortController();
    controller.current = abort;
    if (!regenerate) setPending(text.trim());
    setRegenerating(regenerate);
    setBusy(true); setError(""); setTool(""); setDraft("");
    let conversation = id;
    try {
      if (!conversation) {
        const created = await api<Conversation>("/conversations", json("POST", {document_id: document || null}));
        conversation = created.id;
        await cache.invalidateQueries({queryKey: ["conversations"]});
        navigate("/chat/" + conversation);
      }
      const content = text.trim();
      if (!regenerate) setText("");
      await streamChat(regenerate ? "/chat/regenerate" : "/chat/stream",
        {conversation_id: conversation, model: selected, content}, abort.signal, event => {
          if (event.type === "delta") setDraft(value => value + event.text);
          if (event.type === "tool") setTool(event.name.replaceAll("_", " ") + " · " + event.status);
        });
    } catch (error) {
      if (!abort.signal.aborted) setError((error as Error).message);
    } finally {
      await Promise.all([cache.invalidateQueries({queryKey: ["messages", conversation]}),
        cache.invalidateQueries({queryKey: ["conversations"]}), cache.invalidateQueries({queryKey: ["executions"]})]);
      controller.current = null;
      setDraft(""); setPending(""); setTool(""); setBusy(false); setRegenerating(false);
    }
  }

  return <section className="chat-page">
    <header className="page-top"><strong>Chat</strong>
      <select aria-label="AI model" value={selected} onChange={event => setModel(event.target.value)} disabled={busy}>
        {!selected && <option value="">No model available</option>}
        {models.data?.map(item => <option key={item.id}>{item.id}</option>)}
      </select>
    </header>
    <div className="chat-scroll"><div className="chat-inner">
      {!messages.data?.length && !busy && (!id || messages.isSuccess) && <div className="welcome">
        <span className="hero-icon"><Sparkles size={32}/></span><h1>What can I help you with?</h1>
        <div className="suggestions">{["Summarize this conversation", "What time is it in UTC?", "Find key points in my documents"].map(prompt =>
          <Button key={prompt} onClick={() => setText(prompt)}>{prompt}</Button>)}</div>
      </div>}
      {messages.data?.map((item, index, items) =>
        (!regenerating || item.role !== "assistant" || index !== items.length - 1) &&
        <Message key={item.id} message={item}/>)}
      {pending && !(lastMessage?.role === "user" && lastMessage.content === pending) &&
        <Message message={{id: "pending", role: "user", content: pending}}/>}
      {draft && <Message message={{id: "stream", role: "assistant", content: draft}}/>}
      {busy && <p role="status" className="muted">{tool || (draft ? "Generating…" : "Thinking…")}</p>}
      {messages.error && <p role="alert" className="error">{messages.error.message}</p>}
      {!busy && !!messages.data?.length && <Button variant="ghost" onClick={() => void send(undefined, true)}
        disabled={!selected}><RotateCcw size={15}/> Regenerate</Button>}
      <div ref={end}/>
    </div></div>
    <div className="composer-wrap">
      {(error || models.error) && <p role="alert" className="error">{error || models.error?.message}</p>}
      <form className="composer" onSubmit={send}>
        <textarea aria-label="Message" placeholder="Message Agentic AI…" rows={2} maxLength={12000}
          value={text} onChange={event => setText(event.target.value)} onKeyDown={event => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault(); event.currentTarget.form?.requestSubmit();
            }
          }}/>
        <div className="composer-actions">
          <label className="attach"><FileText size={16}/>
            {!id ? <select aria-label="Attach a document" value={document} onChange={event => setDocument(event.target.value)}>
              <option value="">All documents</option>
              {documents.data?.filter(item => item.processing_status === "ready").map(item =>
                <option key={item.id} value={item.id}>{item.filename}</option>)}
            </select> : <span>{currentDocument?.filename || "All documents"}</span>}
          </label>
          {busy ? <Button aria-label="Stop generation" onClick={() => controller.current?.abort()}><Square size={15}/></Button>
            : <Button type="submit" variant="primary" aria-label="Send message" disabled={!text.trim() || !selected}><ArrowUp size={19}/></Button>}
        </div>
      </form>
    </div>
  </section>;
}
