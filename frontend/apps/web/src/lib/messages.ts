import en from "@/messages/en.json";

// Every string a person reads lives in messages/en.json, never in a component (docs/standards/frontend.md section 7).
// English only (D-054); keys are checked by the compiler, so a typo cannot ship.
type Dict = typeof en;
type Paths<T, P extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${P}${K}` : Paths<T[K], `${P}${K}.`>;
}[keyof T & string];
export type MessageKey = Paths<Dict>;

export function t(key: MessageKey, vars: Record<string, string | number> = {}): string {
  const found = key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en);
  const text = typeof found === "string" ? found : key;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole));
}
