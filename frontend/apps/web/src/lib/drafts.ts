// What a person types survives a failed send, a lost connection and a closed tab (frontend.md section 5): drafts stay on this
// device until sent. Only words the person wrote for a form are kept, never a token, and never a date of birth (D-086: used once,
// not kept). On a shared computer the next person sees none of it: each draft is named by its account (draftName), every draft is
// wiped whenever the session ends however it ends (lib/session.ts), and any other account's drafts are wiped at sign-in.
//
// Storage can be missing or refuse (a private window, blocked site data), so every read and write is guarded and a page works without.

const PREFIX = "colyv-draft:";

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem" | "key" | "length">;

function store(): Store | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

/** A draft's storage name, tied to the account that wrote it. */
export const draftName = (accountId: string, form: string): string => `${accountId}:${form}`;

export function readDraft<T extends object>(name: string, from: Store | null = store()): Partial<T> | null {
  try {
    const raw = from?.getItem(PREFIX + name);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Partial<T>) : null;
  } catch {
    return null;
  }
}

export function saveDraft(name: string, value: object, to: Store | null = store()): void {
  try {
    to?.setItem(PREFIX + name, JSON.stringify(value));
  } catch {
    // Full or refused: the form still works, the draft is just not kept.
  }
}

export function dropDraft(name: string, from: Store | null = store()): void {
  try {
    from?.removeItem(PREFIX + name);
  } catch {
    // Nothing to do.
  }
}

function dropWhere(keep: (name: string) => boolean, from: Store | null): void {
  try {
    if (!from) return;
    const names: string[] = [];
    for (let i = 0; i < from.length; i++) {
      const key = from.key(i);
      if (key?.startsWith(PREFIX) && !keep(key.slice(PREFIX.length))) names.push(key);
    }
    names.forEach((k) => from.removeItem(k));
  } catch {
    // Nothing to do.
  }
}

/** When the session ends, however it ends: every draft, whatever it was for. */
export const dropAllDrafts = (from: Store | null = store()): void => dropWhere(() => false, from);

/** At sign-in: every draft another account left on this device. */
export const dropOtherAccountsDrafts = (accountId: string, from: Store | null = store()): void => dropWhere((name) => name.startsWith(`${accountId}:`), from);
