import {useEffect, useState} from "react";
import {useMutation, useQuery, useQueryClient} from "@tanstack/react-query";
import {Link, NavLink, Navigate, Outlet, Route, Routes, useNavigate, useParams} from "react-router-dom";
import {Activity, FileText, LogOut, Menu, MessageSquare, PanelLeftClose, Pencil, Plus, Settings as Gear, Sparkles, Trash2} from "lucide-react";
import {Button} from "./components/ui/button";
import {Auth, PasswordReset} from "./pages/Auth";
import {Chat, type Conversation} from "./pages/Chat";
import {Documents, Executions, Settings} from "./pages/Workspace";
import {api, json, refresh, setAccess} from "./services/api";
import {useSession, type User} from "./store/session";

function Shell() {
  const [collapsed, setCollapsed] = useState(() => window.matchMedia("(max-width: 700px)").matches);
  const user = useSession(state => state.user)!;
  const setUser = useSession(state => state.setUser);
  const cache = useQueryClient();
  const navigate = useNavigate();
  const {id} = useParams();
  const conversations = useQuery({queryKey: ["conversations"], queryFn: () => api<Conversation[]>("/conversations")});
  const edit = useMutation({mutationFn: ({id, title}: {id: string; title?: string}) => api("/conversations/" + id,
    title ? json("PATCH", {title}) : {method: "DELETE"}), onSuccess: (_, change) => {
      if (!change.title && id === change.id) navigate("/");
      return cache.invalidateQueries({queryKey: ["conversations"]});
    }});
  const logout = useMutation({mutationFn: () => api("/auth/logout", {method: "POST"}, false), onSuccess: () => {
    setAccess(""); cache.clear(); setUser(null); navigate("/login");
  }});
  function closeMobile() {
    if (window.matchMedia("(max-width: 700px)").matches) setCollapsed(true);
  }
  return <div className="shell">
    {!collapsed && <aside className="sidebar">
      <div className="sidebar-top"><Link className="brand" to="/" onClick={closeMobile}>
        <span className="brand-icon"><Sparkles size={18}/></span> Agentic AI</Link>
        <Button aria-label="Collapse sidebar" variant="ghost" onClick={() => setCollapsed(true)}><PanelLeftClose size={18}/></Button>
      </div>
      <Link className="button primary new-chat" to="/" onClick={closeMobile}><Plus size={17}/> New conversation</Link>
      <nav aria-label="Workspace" className="nav">
        <NavLink to="/documents" onClick={closeMobile}><FileText size={17}/> Documents</NavLink>
        <NavLink to="/executions" onClick={closeMobile}><Activity size={17}/> Agent executions</NavLink>
        <NavLink to="/settings" onClick={closeMobile}><Gear size={17}/> Settings</NavLink>
      </nav>
      <div className="history"><h2>Conversations</h2>
        {conversations.data?.map(item => <div className="history-entry" key={item.id}>
          <NavLink to={"/chat/" + item.id} title={item.title} onClick={closeMobile}><MessageSquare size={15}/><span>{item.title}</span></NavLink>
          <Button variant="ghost" aria-label={"Rename " + item.title} onClick={() => {
            const title = window.prompt("Conversation name", item.title)?.trim();
            if (title && title.length <= 160) edit.mutate({id: item.id, title});
          }}><Pencil size={13}/></Button>
          <Button variant="ghost" aria-label={"Delete " + item.title} onClick={() => {
            if (window.confirm("Delete this conversation?")) edit.mutate({id: item.id});
          }}><Trash2 size={13}/></Button>
        </div>)}
      </div>
      {(edit.error || conversations.error || logout.error) && <p className="error" role="alert">
        {edit.error?.message || conversations.error?.message || logout.error?.message}</p>}
      <div className="account"><span className="avatar">{user.full_name.slice(0, 1).toUpperCase()}</span>
        <strong>{user.full_name}</strong><Button variant="ghost" aria-label="Sign out"
          disabled={logout.isPending} onClick={() => logout.mutate()}><LogOut size={17}/></Button></div>
    </aside>}
    <main className="main">
      {collapsed && <Button className="open-sidebar" aria-label="Expand sidebar" onClick={() => setCollapsed(false)}><Menu size={18}/></Button>}
      <Outlet/>
    </main>
  </div>;
}

export function App() {
  const {user, ready, setUser} = useSession();
  useEffect(() => {
    void refresh().then(ok => ok ? api<User>("/auth/me", undefined, false) : null).then(setUser).catch(() => setUser(null));
  }, [setUser]);
  useEffect(() => { document.documentElement.dataset.theme = user?.preferences.theme || "light"; }, [user]);
  if (!ready) return <main className="auth-screen" role="status">Loading your workspace…</main>;
  return <Routes>
    <Route path="/login" element={user ? <Navigate to="/" replace/> : <Auth key="login"/>}/>
    <Route path="/register" element={user ? <Navigate to="/" replace/> : <Auth key="register" register/>}/>
    <Route path="/reset" element={<PasswordReset/>}/>
    <Route element={user ? <Shell/> : <Navigate to="/login" replace/>}>
      <Route index element={<Chat/>}/>
      <Route path="chat/:id" element={<Chat/>}/>
      <Route path="documents" element={<Documents/>}/>
      <Route path="executions" element={<Executions/>}/>
      <Route path="settings" element={<Settings/>}/>
    </Route>
    <Route path="*" element={<Navigate to="/" replace/>}/>
  </Routes>;
}
