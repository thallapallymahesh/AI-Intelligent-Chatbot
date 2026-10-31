import { useEffect, useState } from "react";
import { apiFetch, authConfigured, readSession, recoverPassword, signIn, signOut, signUp, updatePassword } from "./auth";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");
const HELLO = { role: "assistant", content: "Hello! 👋 I'm your AI Intelligent Assistant. How can I help you today?" };

function AuthScreen({ onLogin }) {
  const recovery = new URLSearchParams(window.location.hash.slice(1));
  const recoveryToken = recovery.get("access_token");
  const [mode, setMode] = useState(recovery.get("type") === "recovery" && recoveryToken ? "reset" : "login");
  const [name, setName] = useState(""); const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false); const [notice, setNotice] = useState("");
  async function submit(event) {
    event.preventDefault(); setBusy(true); setNotice("");
    try {
      if (mode === "register") {
        const result = await signUp(name.trim(), email.trim(), password);
        if (result.access_token) onLogin(result);
        else { setNotice("Registration submitted. Check your email to verify the account, then sign in."); setMode("login"); }
      } else if (mode === "forgot") {
        await recoverPassword(email.trim()); setNotice("If that address has an account, a password reset link was sent.");
      } else if (mode === "reset") {
        await updatePassword(password, recoveryToken); setMode("login"); setPassword(""); setNotice("Password updated. Sign in with your new password.");
      } else onLogin(await signIn(email.trim(), password));
    } catch (error) { setNotice(error.message); }
    finally { setBusy(false); }
  }
  return <main className="auth-screen"><form className="auth-card" onSubmit={submit}>
    <div className="logo">🤖 <span>AI Assistant</span></div><h1>{mode === "login" ? "Welcome back" : mode === "register" ? "Create your account" : mode === "reset" ? "Choose a new password" : "Reset password"}</h1>
    {!authConfigured && <p className="auth-warning">Authentication needs Supabase setup. Add VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in Vercel, and the matching Supabase secrets in Render.</p>}
    {mode === "register" && <label>Name<input autoComplete="name" value={name} onChange={e => setName(e.target.value)} required /></label>}
    {mode !== "reset" && <label>Email<input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} required /></label>}
    {mode !== "forgot" && <label>Password<input type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} minLength={8} value={password} onChange={e => setPassword(e.target.value)} required /></label>}
    {notice && <p className="auth-notice">{notice}</p>}
    <button className="auth-submit" disabled={busy || !authConfigured}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : mode === "register" ? "Register" : mode === "reset" ? "Update password" : "Send reset link"}</button>
    <div className="auth-links">{mode === "login" ? <><button type="button" onClick={() => { setMode("register"); setNotice(""); }}>Create account</button><button type="button" onClick={() => { setMode("forgot"); setNotice(""); }}>Forgot password?</button></> : <button type="button" onClick={() => { setMode("login"); setNotice(""); }}>Back to sign in</button>}</div>
  </form></main>;
}

function App() {
  const [session, setSession] = useState(readSession);
  const [chats, setChats] = useState([]); const [currentChatId, setCurrentChatId] = useState(null);
  const [messages, setMessages] = useState([HELLO]); const [input, setInput] = useState("");
  const [uploading, setUploading] = useState(false); const [uploadMessage, setUploadMessage] = useState("");
  const [sending, setSending] = useState(false); const [serviceStatus, setServiceStatus] = useState("checking");
  const [dialog, setDialog] = useState(""); const [theme, setTheme] = useState(localStorage.getItem("chat-theme") || "light");
  const [error, setError] = useState("");
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("chat-theme", theme); }, [theme]);
  useEffect(() => { if (session?.access_token) { loadChats(); checkHealth(); } }, [session]);

  async function checkHealth() {
    try { const response = await fetch(`${API_URL}/api/health`); const data = await response.json();
      setServiceStatus(response.ok && ["healthy", "configured"].includes(data.status) ? "online" : "degraded"); }
    catch { setServiceStatus("offline"); }
  }
  async function loadChats() {
    try { const response = await apiFetch("/api/chats"); if (!response.ok) throw new Error((await response.json()).detail || "Unable to load chats.");
      const data = await response.json(); setChats(data.chats || []); }
    catch (e) { setError(e.message); }
  }
  async function createNewChat() {
    if (sending || uploading) return;
    try { const response = await apiFetch("/api/new-chat", { method: "POST" }); const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not create chat.");
      setCurrentChatId(data.chat_id); setMessages([HELLO]); setInput(""); setUploadMessage(""); await loadChats(); }
    catch (e) { setError(e.message); }
  }
  async function loadChat(id) {
    try { const response = await apiFetch(`/api/chats/${id}`); const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not load chat.");
      setCurrentChatId(id); setMessages(data.messages?.length ? data.messages : [HELLO]); setUploadMessage(""); setError(""); }
    catch (e) { setError(e.message); }
  }
  async function renameChat(chat) {
    const title = window.prompt("Conversation name", chat.title); if (!title?.trim()) return;
    try { const response = await apiFetch(`/api/chats/${chat.id}`, { method: "PATCH", body: JSON.stringify({ title: title.trim() }) });
      if (!response.ok) throw new Error("Could not rename conversation."); await loadChats(); }
    catch (e) { setError(e.message); }
  }
  async function deleteChat(chat) {
    if (!window.confirm(`Delete “${chat.title}” and its uploaded documents?`)) return;
    try { const response = await apiFetch(`/api/chats/${chat.id}`, { method: "DELETE" }); if (!response.ok) throw new Error("Could not delete conversation.");
      if (String(currentChatId) === String(chat.id)) { setCurrentChatId(null); setMessages([HELLO]); }
      await loadChats(); }
    catch (e) { setError(e.message); }
  }
  async function uploadDocument(file) {
    if (!file) return; if (!currentChatId) { setUploadMessage("Please start a new chat first."); return; }
    setUploading(true); setUploadMessage(""); const form = new FormData(); form.append("file", file); form.append("chat_id", currentChatId);
    try { const response = await apiFetch("/api/upload", { method: "POST", body: form }); const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Upload failed."); setUploadMessage(`✅ ${data.filename} indexed (${data.chunks} chunks)`); }
    catch (e) { setUploadMessage(`❌ ${e.message}`); } finally { setUploading(false); }
  }
  async function sendMessage() {
    if (!input.trim() || !currentChatId || sending) return;
    const question = input.trim(); setMessages(previous => [...previous, { role: "user", content: question }]); setInput(""); setSending(true); setUploadMessage("");
    try {
      const response = await apiFetch("/api/chat", { method: "POST", headers: { Accept: "application/x-ndjson" }, body: JSON.stringify({ message: question, chat_id: currentChatId }) });
      if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.detail || `Request failed (${response.status}).`); }
      setMessages(previous => [...previous, { role: "assistant", content: "" }]);
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
      const accept = (line) => { if (!line.trim()) return; const data = JSON.parse(line); if (data.error) throw new Error(data.error);
        setMessages(previous => { const copy = [...previous]; const last = copy.length - 1; if (copy[last]?.role === "assistant") copy[last] = { ...copy[last], ...(data.token ? { content: copy[last].content + data.token } : {}), ...(data.sources ? { sources: data.sources } : {}) }; return copy; }); };
      while (true) { const { value, done } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true }); const lines = buffer.split("\n"); buffer = lines.pop() || ""; lines.forEach(accept); }
      if (buffer.trim()) accept(buffer); await loadChats();
    } catch (e) { setError(e.message); }
    finally { setSending(false); }
  }
  async function logout() { await signOut(); setSession(null); setChats([]); setCurrentChatId(null); setMessages([HELLO]); }

  if (!session?.access_token) return <AuthScreen onLogin={value => { localStorage.setItem("ai-chatbot-session", JSON.stringify(value)); setSession(value); }} />;
  return <div className="app">
    <aside className="sidebar"><div className="logo">🤖 <span>AI Assistant</span></div>
      <button className="new-chat" onClick={createNewChat} disabled={sending || uploading}>+ New Chat</button>
      <div className="chat-history"><p className="history-title">Recent Chats</p>
        {chats.length === 0 ? <p className="no-chats">No conversations yet</p> : chats.map(chat => <div key={chat.id} className={`history-item ${String(currentChatId) === String(chat.id) ? "active" : ""}`}>
          <button className="chat-select" onClick={() => loadChat(chat.id)}>💬 {chat.title}</button><span className="chat-actions"><button title="Rename" onClick={() => renameChat(chat)}>✎</button><button title="Delete" onClick={() => deleteChat(chat)}>×</button></span>
        </div>)}
      </div>
      <div className="sidebar-bottom"><div className="account-email">{session.user?.email || "Signed in"}</div><button onClick={() => setDialog("settings")}>⚙️ Settings</button><button onClick={() => setDialog("help")}>❓ Help</button><button onClick={logout}>↪ Sign out</button></div>
    </aside>
    <main className="chat-container"><header className="chat-header"><div><h1>AI Intelligent Assistant</h1><p><span className="status-dot" />{serviceStatus === "online" ? "Online" : serviceStatus === "checking" ? "Checking service…" : serviceStatus === "degraded" ? "AI needs configuration" : "Backend unavailable"}</p></div></header>
      {error && <div className="app-error" role="alert">{error}<button onClick={() => setError("")}>Dismiss</button></div>}
      <section className="messages">{messages.map((message, index) => <div key={`${index}-${message.role}`} className={`message-row ${message.role}`}><div className="avatar">{message.role === "assistant" ? "🤖" : "👤"}</div><div className="message">{message.content}{message.sources?.length > 0 && <div className="sources"><div className="sources-title">📚 Sources</div>{message.sources.map((source, i) => <div className="source-item" key={i}>📄 {source.filename}<span> — Chunk {source.chunk + 1}</span></div>)}</div>}</div></div>)}{sending && <div className="message-row assistant"><div className="avatar">🤖</div><div className="message">Thinking…</div></div>}</section>
      <div className="input-area"><div className="input-box"><label className="attach-button">📎<input type="file" accept=".pdf,.docx,.txt" disabled={uploading} onChange={e => { uploadDocument(e.target.files[0]); e.target.value = ""; }} /></label><input type="text" placeholder={currentChatId ? "Ask anything…" : "Click + New Chat first…"} value={input} disabled={sending || !currentChatId} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) sendMessage(); }} /><button className="send-button" onClick={sendMessage} disabled={sending || !input.trim() || !currentChatId}>➤</button></div><p className="input-note">{uploading ? "Uploading and indexing document…" : uploadMessage || (sending ? "AI is generating a response…" : "PDF, DOCX and TXT are supported. AI can make mistakes.")}</p></div>
    </main>
    {dialog && <div className="modal-backdrop" role="presentation" onClick={() => setDialog("")}><section className="settings-modal" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}><button className="modal-close" onClick={() => setDialog("")}>×</button>
      {dialog === "settings" ? <><h2>Settings</h2><p>Account: {session.user?.email}</p><label className="setting-row">Theme<select value={theme} onChange={e => setTheme(e.target.value)}><option value="light">Light</option><option value="dark">Dark</option></select></label><p>Chat history and documents are private to your account.</p><button className="danger-button" onClick={async () => { if (window.confirm("Permanently clear all your chats and uploaded documents?")) { const r = await apiFetch("/api/chats", { method: "DELETE" }); if (r.ok) { setChats([]); setCurrentChatId(null); setMessages([HELLO]); } else setError("Could not clear chat history."); } }}>Clear all chat history</button></> : <><h2>Help</h2><h3>Getting started</h3><p>Sign in, select + New Chat, then ask your question.</p><h3>Document questions</h3><p>Attach a text based PDF, DOCX or TXT document (up to 10 MB), wait for indexing, then ask about its contents.</p><h3>Retrieval and citations</h3><p>The assistant searches relevant document passages and shows filenames and chunk numbers below its answer when available.</p><h3>Troubleshooting</h3><p>If AI is unavailable, the backend needs a configured provider API key and supported chat and embedding models. Uploads require readable text and a configured vector database.</p></>}
    </section></div>}
  </div>;
}

export default App;
