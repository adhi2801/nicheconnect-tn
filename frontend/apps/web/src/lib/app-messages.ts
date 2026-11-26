import app from "@/messages/en-app.json";
import base from "@/messages/en.json";

// The signed-in screens' words: the shared catalogue (messages/en.json) and the signed-in one (messages/en-app.json) together.
// Kept apart so the public pages (landing, sign-in), which import lib/messages.ts, never ship the signed-in screens' copy: every
// page bundles the whole catalogue it imports, and Lighthouse holds public pages to a JavaScript ratchet (D-198).
// Keys are checked by the compiler across both files, so a typo cannot ship; a key in both would be ambiguous, so none may be.
type Dict = typeof base & typeof app;
type Paths<T, P extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : Paths<T[K], `${P}${K}.`>;
}[keyof T & string];
export type MessageKey = Paths<Dict>;

const dict: Record<string, unknown> = { ...base, ...app };

export function t(key: MessageKey, vars: Record<string, string | number> = {}): string {
  const found = key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], dict);
  const text = typeof found === "string" ? found : key;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole));
}
