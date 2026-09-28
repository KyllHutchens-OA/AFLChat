// A simple local list of recent conversations (id, first question, date) for
// the chat history drawer, plus a "last conversation" pointer so returning to
// /ask restores the previous thread. Both are local-only: no server list
// exists (conversations aren't tied to an account), so this is best-effort
// and per-browser, same as the owner tokens it's stored next to.
const RECENT_KEY = 'footy-nac-recent-conversations';
const LAST_KEY = 'footy-nac-last-conversation';
const MAX_RECENT = 20;

export interface RecentConversation {
  id: string;
  firstQuestion: string;
  date: string; // ISO
}

const readJson = <T,>(key: string, fallback: T): T => {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
};

const writeJson = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage unavailable (private mode) — the list just won't persist
  }
};

export function getRecentConversations(): RecentConversation[] {
  return readJson<RecentConversation[]>(RECENT_KEY, []);
}

export function addRecentConversation(id: string, firstQuestion: string): void {
  const existing = getRecentConversations().filter((c) => c.id !== id);
  const next = [{ id, firstQuestion: firstQuestion.slice(0, 140), date: new Date().toISOString() }, ...existing]
    .slice(0, MAX_RECENT);
  writeJson(RECENT_KEY, next);
}

export function getLastConversationId(): string | null {
  try {
    return localStorage.getItem(LAST_KEY);
  } catch {
    return null;
  }
}

export function setLastConversationId(id: string | null): void {
  try {
    if (id) localStorage.setItem(LAST_KEY, id);
    else localStorage.removeItem(LAST_KEY);
  } catch {
    // ignore
  }
}
