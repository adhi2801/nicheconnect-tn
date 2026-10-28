// The signed-in state of this browser tab.
//
// The access token lives here, in memory only (docs/standards/frontend.md section 10). The refresh token is never here: it is in an
// httpOnly cookie that only app/api/session reads. So a reload asks /api/session/refresh for a new access token, and the page's
// own scripts can never read a long-lived credential.
export type Role = "creator" | "brand";
export type Session = { role: Role; accountId: string; accessToken: string; expiresAt: number };
export type SessionState = { status: "restoring" } | { status: "signedOut" } | { status: "signedIn"; session: Session };

type Granted = { access_token: string; expires_in: number; account: { id: string; role: string } };

const RESTORING: SessionState = { status: "restoring" };
const SIGNED_OUT: SessionState = { status: "signedOut" };
const RENEW_BEFORE_EXPIRY_MS = 60_000;

let state: SessionState = RESTORING;
let timer: ReturnType<typeof setTimeout> | undefined;
let inFlight: Promise<boolean> | null = null;
const listeners = new Set<() => void>();
const channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("colyv-session");

export const getSessionState = (): SessionState => state;
export const getServerSessionState = (): SessionState => RESTORING;
export const getAccessToken = (): string | null => (state.status === "signedIn" ? state.session.accessToken : null);

export function subscribeToSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function set(next: SessionState): void {
  state = next;
  clearTimeout(timer);
  if (next.status === "signedIn") {
    const wait = Math.max(5_000, next.session.expiresAt - Date.now() - RENEW_BEFORE_EXPIRY_MS);
    timer = setTimeout(() => void renewSession(), wait);
  }
  listeners.forEach((l) => l());
}

const fromGrant = (g: Granted): Session => ({ role: g.account.role === "brand" ? "brand" : "creator", accountId: g.account.id, accessToken: g.access_token, expiresAt: Date.now() + g.expires_in * 1000 });

/** Called after a login code is accepted. Tells the person's other tabs. */
export function startSession(grant: Granted): void {
  const session = fromGrant(grant);
  set({ status: "signedIn", session });
  channel?.postMessage({ type: "signedIn", session });
}

// One tab renews at a time, so the backend never sees the same refresh token twice (it would treat that as a stolen copy and end
// every session). Within a tab, callers share one request; across tabs, a lock makes them take turns, and a tab that waited
// uses the token another tab already fetched.
async function withLock<T>(task: () => Promise<T>): Promise<T> {
  return typeof navigator !== "undefined" && navigator.locks ? navigator.locks.request("colyv-refresh", task) : task();
}

export function renewSession(): Promise<boolean> {
  if (inFlight) return inFlight;
  // Remember what we held before waiting for the lock. If it is newer afterwards, another tab renewed while we waited.
  const heldBefore = state.status === "signedIn" ? state.session.expiresAt : 0;
  inFlight = withLock(async () => {
    if (state.status === "signedIn" && state.session.expiresAt > heldBefore) return true;
    try {
      const response = await fetch("/api/session/refresh", { method: "POST", cache: "no-store" });
      if (response.ok) {
        const session = fromGrant((await response.json()) as Granted);
        set({ status: "signedIn", session });
        channel?.postMessage({ type: "signedIn", session });
        return true;
      }
      if (response.status === 401 || response.status === 422) {
        set(SIGNED_OUT);
        return false;
      }
    } catch {
      // Offline or the backend is busy: the person is still signed in, so keep what we have and try again later.
    }
    if (state.status === "restoring") set(SIGNED_OUT);
    return false;
  }).finally(() => {
    inFlight = null;
  });
  return inFlight;
}

/** Called once when a screen that needs a person opens: signs back in from the cookie, if there is one. */
export function restoreSession(): Promise<boolean> {
  return state.status === "restoring" ? renewSession() : Promise.resolve(state.status === "signedIn");
}

export async function signOut(): Promise<void> {
  set(SIGNED_OUT);
  channel?.postMessage({ type: "signedOut" });
  await fetch("/api/session/logout", { method: "POST", cache: "no-store" }).catch(() => undefined);
}

// Another tab signed in, renewed or signed out: follow it, without telling the others again.
channel?.addEventListener("message", (event: MessageEvent<{ type: string; session?: Session }>) => {
  if (event.data.type === "signedIn" && event.data.session) set({ status: "signedIn", session: event.data.session });
  if (event.data.type === "signedOut") set(SIGNED_OUT);
});
