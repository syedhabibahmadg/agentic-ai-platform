import {useState, type FormEvent} from "react";
import {Link, useNavigate} from "react-router-dom";
import {ArrowRight, Sparkles} from "lucide-react";
import {Button} from "../components/ui/button";
import {api, json, setAccess} from "../services/api";
import {useSession, type User} from "../store/session";

export function Auth({register = false}: {register?: boolean}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const setUser = useSession(state => state.setUser);
  const navigate = useNavigate();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const form = Object.fromEntries(new FormData(event.currentTarget));
    if (register && form.password !== form.confirm) {
      setError("Passwords must match");
      return;
    }
    setBusy(true);
    try {
      const token = await api<{access_token: string}>("/auth/" + (register ? "register" : "login"),
        json("POST", {email: form.email, password: form.password, full_name: form.full_name}), false);
      setAccess(token.access_token);
      setUser(await api<User>("/auth/me"));
      navigate("/", {replace: true});
    } catch (error) {
      setError((error as Error).message);
    } finally { setBusy(false); }
  }

  return <main className="auth-screen">
    <section className="auth-card">
      <div className="brand"><span className="brand-icon"><Sparkles size={20}/></span> Agentic AI</div>
      <h1>{register ? "Create your account" : "Welcome back"}</h1>
      <form onSubmit={submit}>
        {register && <label>Full name<input name="full_name" autoComplete="name" maxLength={100} required/></label>}
        <label>Email address<input name="email" type="email" autoComplete="email" required/></label>
        <label>Password<input name="password" type="password" autoComplete={register ? "new-password" : "current-password"}
          minLength={register ? 12 : 1} maxLength={128} required/></label>
        {register && <label>Confirm password<input name="confirm" type="password" autoComplete="new-password"
          minLength={12} maxLength={128} required/></label>}
        {error && <p role="alert" className="error">{error}</p>}
        <Button variant="primary" type="submit" disabled={busy}>{register ? "Create account" : "Sign in"}<ArrowRight size={16}/></Button>
      </form>
      <p className="muted">{register ? "Already have an account?" : "New to Agentic AI?"}{" "}
        <Link to={register ? "/login" : "/register"}>{register ? "Sign in" : "Create an account"}</Link></p>
      {!register && <Link to="/reset">Forgot password?</Link>}
    </section>
  </main>;
}

export function PasswordReset() {
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get("token"));
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true); setError("");
    try {
      if (token) {
        if (data.password !== data.confirm) throw new Error("Passwords must match");
        await api("/auth/password-reset/confirm", json("POST", {token, password: data.password}), false);
        navigate("/login", {replace: true});
      } else {
        const result = await api<{message: string}>("/auth/password-reset/request",
          json("POST", {email: data.email}), false);
        setMessage(result.message);
      }
    } catch (error) {
      setError((error as Error).message);
    } finally { setBusy(false); }
  }
  return <main className="auth-screen"><section className="auth-card">
    <h1>Reset password</h1>
    <form onSubmit={submit}>
      {token ? <>
        <label>New password<input type="password" name="password" minLength={12} maxLength={128} autoComplete="new-password" required/></label>
        <label>Confirm password<input type="password" name="confirm" minLength={12} maxLength={128} autoComplete="new-password" required/></label>
      </> : <label>Email address<input type="email" name="email" autoComplete="email" required/></label>}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert" className="error">{error}</p>}
      <Button type="submit" variant="primary" disabled={busy}>{token ? "Save password" : "Send reset link"}</Button>
    </form>
    <Link to="/login">Back to sign in</Link>
  </section></main>;
}
