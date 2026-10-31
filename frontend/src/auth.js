const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, "");
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;
const SESSION_KEY = "ai-chatbot-session";

const LOCAL_DEV_TOKEN = import.meta.env.VITE_LOCAL_DEV_TOKEN || "";
const localAuth = import.meta.env.DEV && import.meta.env.VITE_LOCAL_AUTH === "true" && Boolean(LOCAL_DEV_TOKEN);
export const authConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY) || localAuth;
export const readSession = () => {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY) || "null"); }
  catch { return null; }
};
const saveSession = (session) => {
  if (session?.expires_in && !session.expires_at) session.expires_at = Math.floor(Date.now() / 1000) + session.expires_in;
  if (session?.access_token) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else localStorage.removeItem(SESSION_KEY);
  return session;
};
async function authRequest(path, body, token) {
  const response = await fetch(`${SUPABASE_URL}/auth/v1/${path}`, {
    method: "POST",
    headers: { apikey: SUPABASE_ANON_KEY, "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.msg || data.message || data.error_description || data.error || "Authentication request failed.");
  return data;
}
export async function signIn(email, password) {
  if (localAuth) return saveSession({ access_token: LOCAL_DEV_TOKEN, user: { email: email || "local@localhost", user_metadata: { name: "Local developer" } } });
  return saveSession(await authRequest("token?grant_type=password", { email, password }));
}
export async function signUp(name, email, password) {
  if (localAuth) return { access_token: LOCAL_DEV_TOKEN, user: { email, user_metadata: { name } } };
  return authRequest("signup", { email, password, data: { name } });
}
export async function recoverPassword(email) {
  if (localAuth) throw new Error("Password reset is available when Supabase Auth is configured.");
  return authRequest("recover", { email, redirect_to: window.location.origin });
}
export async function updatePassword(password, token) {
  const response = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
    method: "PUT",
    headers: { apikey: SUPABASE_ANON_KEY, "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ password }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.msg || data.message || "Unable to update password.");
  window.history.replaceState({}, document.title, window.location.pathname);
}
export async function signOut() {
  const session = readSession();
  try { if (session?.access_token) await authRequest("logout", undefined, session.access_token); }
  finally { saveSession(null); }
}
export async function accessToken() {
  let session = readSession();
  if (!session?.access_token) return null;
  if (session.expires_at && session.expires_at * 1000 < Date.now() + 30000 && session.refresh_token) {
    try {
      const refreshed = await authRequest("token?grant_type=refresh_token", { refresh_token: session.refresh_token });
      session = saveSession(refreshed);
    } catch { saveSession(null); return null; }
  }
  return session.access_token;
}
export async function apiFetch(path, options = {}) {
  const token = await accessToken();
  if (!token) throw new Error("Please sign in again to continue.");
  return fetch(`${import.meta.env.VITE_API_URL || ""}${path}`, {
    ...options,
    headers: { ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...options.headers, Authorization: `Bearer ${token}` },
  });
}
