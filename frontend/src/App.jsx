import { useCallback, useEffect, useRef, useState } from "react";
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
  const [archivedView, setArchivedView] = useState(false); const [chatSearch, setChatSearch] = useState("");
  const [documents, setDocuments] = useState([]); const [retryQuestion, setRetryQuestion] = useState("");
  const [messages, setMessages] = useState([HELLO]); const [input, setInput] = useState("");
  const [uploading, setUploading] = useState(false); const [uploadMessage, setUploadMessage] = useState("");
  const [sending, setSending] = useState(false); const [serviceStatus, setServiceStatus] = useState("checking");
  const [dialog, setDialog] = useState(""); const [theme, setTheme] = useState(localStorage.getItem("chat-theme") || "light");
  const [error, setError] = useState("");
  const [generationId, setGenerationId] = useState(null); const controllerRef = useRef(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("chat-theme", theme); }, [theme]);
  async function checkHealth() {
    try { const response = await fetch(`${API_URL}/api/health`); const data = await response.json();
      setServiceStatus(response.ok && ["healthy", "configured"].includes(data.status) ? "online" : "degraded"); }
    catch { setServiceStatus("offline"); }
  }
  const loadChats = useCallback(async (archived = archivedView) => {
    try { const response = await apiFetch(`/api/chats?archived=${archived}`); if (!response.ok) throw new Error((await response.json()).detail || "Unable to load chats.");
      const data = await response.json(); setChats(data.chats || []); }
    catch (e) { setError(e.message); }
  }, [archivedView]);
  useEffect(() => {
    if (!session?.access_token) return undefined;
    const timer = window.setTimeout(() => { loadChats(archivedView); checkHealth(); }, 0);
    return () => window.clearTimeout(timer);
  }, [session, archivedView, loadChats]);
  async function loadDocuments(chatId) {
    if (!chatId) { setDocuments([]); return; }
    try { const response = await apiFetch(`/api/chats/${chatId}/documents`); const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Unable to load documents."); setDocuments(data.documents || []); }
    catch (e) { setError(e.message); }
  }
  async function createNewChat() {
    if (sending || uploading) return;
    try { const response = await apiFetch("/api/new-chat", { method: "POST" }); const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not create chat.");
      setCurrentChatId(data.chat_id); setMessages([HELLO]); setDocuments([]); setInput(""); setUploadMessage(""); await loadChats(); }
    catch (e) { setError(e.message); }
  }
  async function loadChat(id) {
    try { const response = await apiFetch(`/api/chats/${id}`); const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not load chat.");
      setCurrentChatId(id); setMessages(data.messages?.length ? data.messages : [HELLO]); setUploadMessage(""); setError(""); await loadDocuments(id); }
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
      if (String(currentChatId) === String(chat.id)) { setCurrentChatId(null); setMessages([HELLO]); setDocuments([]); }
      await loadChats(); }
    catch (e) { setError(e.message); }
  }
  async function uploadDocument(files) {
    const fileList = Array.from(files || []); if (!fileList.length) return;
    if (!currentChatId) { setUploadMessage("Please start a new chat first."); return; }
    setUploading(true); setUploadMessage(""); const completed = []; const failures = [];
    for (const file of fileList) {
      const form = new FormData(); form.append("file", file); form.append("chat_id", currentChatId);
      try { const response = await apiFetch("/api/upload", { method: "POST", body: form }); const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Upload failed."); completed.push(`${data.filename} (${data.chunks})`); }
      catch (e) { failures.push(`${file.name}: ${e.message}`); }
    }
    setUploadMessage(`${completed.length ? `✅ Indexed: ${completed.join(", ")}` : ""}${failures.length ? ` ❌ ${failures.join("; ")}` : ""}`);
    await loadDocuments(currentChatId); setUploading(false);
  }
  async function sendMessage(overrideQuestion, options = {}) {
    const question = (overrideQuestion ?? input).trim();
    if (!question || !currentChatId || sending) return;
    const { regenerate = false, action = "chat" } = options;
    if (regenerate) setMessages(previous => previous.slice(0, -1));
    else setMessages(previous => [...previous, { role: "user", content: question }]);
    setRetryQuestion(question); setInput(""); setSending(true); setUploadMessage(""); setError("");
    controllerRef.current = new AbortController();
    try {
      const response = await apiFetch("/api/chat", { method: "POST", signal: controllerRef.current.signal,
        headers: { Accept: "application/x-ndjson" }, body: JSON.stringify({ message: question, chat_id: currentChatId, regenerate, action }) });
      if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.detail || `Request failed (${response.status}).`); }
      const streamId = response.headers.get("X-Generation-ID"); setGenerationId(streamId);
      setMessages(previous => [...previous, { role: "assistant", content: "" }]);
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = "";
      const accept = (line) => { if (!line.trim()) return; const data = JSON.parse(line); if (data.error) throw new Error(data.error);
        setMessages(previous => { const copy = [...previous]; const last = copy.length - 1; if (copy[last]?.role === "assistant") copy[last] = { ...copy[last], ...(data.token ? { content: copy[last].content + data.token } : {}), ...(data.sources ? { sources: data.sources } : {}) }; return copy; }); };
      while (true) { const { value, done } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true }); const lines = buffer.split("\n"); buffer = lines.pop() || ""; lines.forEach(accept); }
      if (buffer.trim()) accept(buffer); await loadChats(); await loadChat(currentChatId);
    } catch (e) { if (e.name !== "AbortError") setError(e.message); }
    finally { controllerRef.current = null; setGenerationId(null); setSending(false); }
  }
  async function stopGeneration() {
    if (generationId) await apiFetch("/api/chat/stop", { method: "POST", body: JSON.stringify({ generation_id: generationId }) }).catch(() => {});
    controllerRef.current?.abort();
  }
  async function archiveChat(chat) {
    try { const response = await apiFetch(`/api/chats/${chat.id}`, { method: "PATCH", body: JSON.stringify({ archived: !archivedView }) });
      if (!response.ok) throw new Error("Could not update archive status."); await loadChats();
      if (String(currentChatId) === String(chat.id) && !archivedView) { setCurrentChatId(null); setMessages([HELLO]); setDocuments([]); } }
    catch (e) { setError(e.message); }
  }
  async function deleteDocument(document) {
    if (!window.confirm(`Remove ${document.filename} and its indexed chunks?`)) return;
    try { const response = await apiFetch(`/api/chats/${currentChatId}/documents/${document.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Could not remove document."); await loadDocuments(currentChatId); }
    catch (e) { setError(e.message); }
  }
  async function setFeedback(message, feedback) {
    if (!message.id) return;
    try { const response = await apiFetch(`/api/chats/${currentChatId}/messages/${message.id}/feedback`, { method: "PATCH", body: JSON.stringify({ feedback }) });
      if (!response.ok) throw new Error("Could not save feedback.");
      setMessages(previous => previous.map(item => item.id === message.id ? { ...item, feedback } : item)); }
    catch (e) { setError(e.message); }
  }
  async function exportHistory() {
    try { const response = await apiFetch("/api/chats/export"); const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Export failed.");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = "ai-chat-history.json"; link.click(); URL.revokeObjectURL(url); }
    catch (e) { setError(e.message); }
  }
  async function deleteAccount() {
    if (deleteConfirmation !== "DELETE") return;
    try { const response = await apiFetch("/api/account", { method: "DELETE" }); if (!response.ok) throw new Error((await response.json()).detail || "Account deletion failed.");
      localStorage.removeItem("ai-chatbot-session"); setSession(null); setChats([]); setDocuments([]); setDialog(""); }
    catch (e) { setError(e.message); }
  }
  async function logout() { await signOut(); setSession(null); setChats([]); setCurrentChatId(null); setMessages([HELLO]); }

  const visibleChats = chats.filter(chat => (chat.title || "").toLowerCase().includes(chatSearch.toLowerCase()));
  const lastAssistantIndex = messages.map(message => message.role).lastIndexOf("assistant");
  const lastUser = [...messages].reverse().find(message => message.role === "user");

  if (!session?.access_token) return <AuthScreen onLogin={value => { localStorage.setItem("ai-chatbot-session", JSON.stringify(value)); setSession(value); }} />;
  return <div className="app">
    <aside className="sidebar"><div className="logo">🤖 <span>AI Assistant</span></div>
      <button className="new-chat" onClick={createNewChat} disabled={sending || uploading}>+ New Chat</button>
      <div className="chat-history"><input className="chat-search" placeholder="Search chats" value={chatSearch} onChange={e => setChatSearch(e.target.value)} />
        <button className="archive-toggle" onClick={() => setArchivedView(value => !value)}>{archivedView ? "← Recent chats" : "Archived chats"}</button>
        <p className="history-title">{archivedView ? "Archived" : "Recent Chats"}</p>
        {visibleChats.length === 0 ? <p className="no-chats">{chatSearch ? "No matches" : archivedView ? "No archived chats" : "No conversations yet"}</p> : visibleChats.map(chat => <div key={chat.id} className={`history-item ${String(currentChatId) === String(chat.id) ? "active" : ""}`}>
          <button className="chat-select" onClick={() => loadChat(chat.id)}>💬 {chat.title}</button><span className="chat-actions"><button title="Rename" onClick={() => renameChat(chat)}>✎</button><button title={archivedView ? "Restore" : "Archive"} onClick={() => archiveChat(chat)}>{archivedView ? "↩" : "▣"}</button><button title="Delete" onClick={() => deleteChat(chat)}>×</button></span>
        </div>)}
      </div>
      <div className="sidebar-bottom"><div className="account-email">{session.user?.email || "Signed in"}</div><button onClick={() => setDialog("settings")}>⚙️ Settings</button><button onClick={() => setDialog("help")}>❓ Help</button><button onClick={logout}>↪ Sign out</button></div>
    </aside>
    <main className="chat-container"><header className="chat-header"><div><h1>AI Intelligent Assistant</h1><p><span className="status-dot" />{serviceStatus === "online" ? "Online" : serviceStatus === "checking" ? "Checking service…" : serviceStatus === "degraded" ? "AI needs configuration" : "Backend unavailable"}</p></div></header>
      {error && <div className="app-error" role="alert"><span>{error}</span><div>{retryQuestion && !sending && <button onClick={() => sendMessage(retryQuestion, { regenerate: true })}>Retry</button>}<button onClick={() => setError("")}>Dismiss</button></div></div>}
      {currentChatId && <details className="document-panel"><summary>Documents ({documents.length})</summary><div className="document-list">{documents.length ? documents.map(document => <div key={document.id}><span>📄 {document.filename} · {document.chunks ?? document.chunk_count ?? 0} chunks</span><button onClick={() => deleteDocument(document)} title="Remove document">×</button></div>) : <p>No documents attached to this chat.</p>}</div></details>}
      <section className="messages">{messages.map((message, index) => <div key={`${message.id || index}-${message.role}`} className={`message-row ${message.role}`}><div className="avatar">{message.role === "assistant" ? "🤖" : "👤"}</div><div className="message">{message.content}{message.sources?.length > 0 && <div className="sources"><div className="sources-title">📚 Sources</div>{message.sources.map((source, i) => <div className="source-item" key={i}>📄 {source.filename}<span>{source.page ? ` — Page ${source.page}` : ""} — Chunk {source.chunk + 1}</span></div>)}</div>}{message.role === "assistant" && message.content && <div className="response-actions"><button onClick={() => navigator.clipboard?.writeText(message.content).catch(() => setError("Clipboard access was blocked."))}>Copy</button>{index === lastAssistantIndex && lastUser && <button disabled={sending} onClick={() => sendMessage(lastUser.content, { regenerate: true })}>Regenerate</button>}{message.id && <><button className={message.feedback === 1 ? "selected" : ""} aria-label="Helpful" onClick={() => setFeedback(message, 1)}>👍</button><button className={message.feedback === -1 ? "selected" : ""} aria-label="Not helpful" onClick={() => setFeedback(message, -1)}>👎</button></>}</div>}</div></div>)}{sending && <div className="message-row assistant"><div className="avatar">🤖</div><div className="message">Generating response…</div></div>}</section>
      <div className="input-area"><div className="quick-actions"><button disabled={!currentChatId || sending} onClick={() => sendMessage("Summarize my uploaded documents", { action: "summary" })}>Summarize</button><button disabled={!currentChatId || sending} onClick={() => sendMessage("List key points from the uploaded documents", { action: "key_points" })}>Key points</button><button disabled={!currentChatId || sending} onClick={() => sendMessage("Generate a quiz from my uploaded documents", { action: "quiz" })}>Create quiz</button></div><div className="input-box"><label className="attach-button">📎<input type="file" multiple accept=".pdf,.docx,.txt" disabled={uploading} onChange={e => { uploadDocument(e.target.files); e.target.value = ""; }} /></label><input type="text" placeholder={currentChatId ? "Ask anything…" : "Click + New Chat first…"} value={input} disabled={sending || !currentChatId} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) sendMessage(); }} /><button className="send-button" onClick={() => sendMessage()} disabled={sending || !input.trim() || !currentChatId}>➤</button>{sending && <button className="stop-button" onClick={stopGeneration}>Stop</button>}</div><p className="input-note">{uploading ? "Uploading and indexing selected documents…" : uploadMessage || (sending ? "AI is generating a response…" : "PDF, DOCX and TXT are supported. AI can make mistakes.")}</p></div>
    </main>
    {dialog && <div className="modal-backdrop" role="presentation" onClick={() => setDialog("")}><section className="settings-modal" role="dialog" aria-modal="true" onClick={e => e.stopPropagation()}><button className="modal-close" onClick={() => setDialog("")}>×</button>
      {dialog === "settings" ? <><h2>Settings & account</h2><p>Signed in as: {session.user?.email}</p><label className="setting-row">Theme<select value={theme} onChange={e => setTheme(e.target.value)}><option value="light">Light</option><option value="dark">Dark</option></select></label><button onClick={exportHistory}>Download chat history (JSON)</button><button className="danger-button" onClick={async () => { if (window.confirm("Permanently clear all your chats and uploaded documents?")) { const r = await apiFetch("/api/chats", { method: "DELETE" }); if (r.ok) { setChats([]); setDocuments([]); setCurrentChatId(null); setMessages([HELLO]); } else setError("Could not clear chat history."); } }}>Clear all chat history</button><hr /><h3>Delete account</h3><p>This permanently deletes your account, chats, documents and vectors. Type DELETE to confirm.</p><input aria-label="Type DELETE to confirm" value={deleteConfirmation} onChange={e => setDeleteConfirmation(e.target.value)} /><button className="danger-button" disabled={deleteConfirmation !== "DELETE"} onClick={deleteAccount}>Delete my account</button></> : <><h2>Help</h2><h3>Getting started</h3><p>Sign in, select + New Chat, then ask your question. Search recent chats by title; archive or restore chats from their menu.</p><h3>Document questions</h3><p>Attach one or more text based PDF, DOCX or TXT documents (10 MB each). PDF citations include page numbers; other formats show chunk references.</p><h3>Document tools</h3><p>Use Summarize, Key points or Create quiz after attaching documents. Answers depend on the configured AI provider and retrieved passages.</p><h3>Security and troubleshooting</h3><p>Sessions and private chat access use Supabase Auth. Repeated chat or upload requests are limited per account. Auth email verification and sign-in throttling follow Supabase project settings. Retry failed generation from the error banner.</p></>}
    </section></div>}
  </div>;
}

export default App;
