import { deviceWords, type AttentionItem, type Row } from "@/lib/attention";
import { t } from "@/lib/messages";

/** The row's title in words. A new sign-in names the device the app gave, else what it said it is. */
export function titleFor(row: Row, item: AttentionItem): string {
  if (row.kind !== "new_sign_in") return t(row.titleKey, row.titleVars);
  const d = deviceWords(item);
  return t(row.titleKey, { ...row.titleVars, device: d.label ?? t(d.fallbackKey) });
}
