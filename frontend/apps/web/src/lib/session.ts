import { setAccessToken } from "./api";

// Held in memory only, never localStorage (docs/standards/frontend.md section 7). A full page reload signs the person out
// until the refresh-token design is approved (a security decision, CLAUDE.md section 5).
export type Role = "creator" | "brand";
export type Session = { role: Role; isNew: boolean; accountId: string; refreshToken: string };

let current: Session | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

export const getSession = (): Session | null => current;

/** For React's useSyncExternalStore: screens re-render when the person signs in or out. */
export function subscribeToSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function startSession(s: Session, accessToken: string): void {
  current = s;
  setAccessToken(accessToken);
  notify();
}

export function endSession(): void {
  current = null;
  setAccessToken(null);
  notify();
}
