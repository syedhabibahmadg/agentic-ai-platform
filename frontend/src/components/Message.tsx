import {useState, type ReactNode} from "react";
import {Copy, Sparkles} from "lucide-react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type {Source} from "../services/api";
import {Button} from "./ui/button";
import "highlight.js/styles/github-dark.css";

export type ChatMessage = {id: string; role: string; content: string; created_at?: string; sources?: Source[]};

function CodeBlock({children}: {children: ReactNode}) {
  const [label, setLabel] = useState("Copy code");
  return <div className="code-block"><Button variant="ghost" onClick={async event => {
    const text = event.currentTarget.parentElement?.querySelector("code")?.textContent || "";
    try { await navigator.clipboard.writeText(text); setLabel("Copied"); }
    catch { setLabel("Copy failed"); }
  }}><Copy size={13}/>{label}</Button><pre>{children}</pre></div>;
}

export function Message({message}: {message: ChatMessage}) {
  const assistant = message.role === "assistant";
  return <article className={assistant ? "message assistant" : "message user-message"}>
    {assistant && <span className="message-icon"><Sparkles size={16}/></span>}
    <div className="message-body">
      <div className="message-meta">{assistant ? "Assistant" : "You"} {message.created_at &&
        <time dateTime={message.created_at}>{new Date(message.created_at).toLocaleTimeString([], {
          hour: "numeric", minute: "2-digit",
        })}</time>}</div>
      {assistant ? <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}
        components={{pre: ({children}) => <CodeBlock>{children}</CodeBlock>, img: () => null}}>
        {message.content}
      </Markdown> : <p>{message.content}</p>}
      {!!message.sources?.length && <ul className="sources" aria-label="Document sources">{message.sources.map((source, i) =>
        <li key={i}>{source.filename} · Chunk {source.chunk}</li>)}</ul>}
    </div>
  </article>;
}
