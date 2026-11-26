import { flagWords } from "@/lib/campaigns";
import { t } from "@/lib/app-messages";
import { AlertIcon } from "./icons";

/** Warnings shown beside the text they are about, never hiding it (trust-and-safety.md section 5, ux.md section 5). */
export function FlagNote({ flags }: { flags: readonly string[] }) {
  if (flags.length === 0) return null;
  return (
    <ul className="grid gap-1.5">
      {flags.map((flag) => (
        <li key={flag} className="flex items-start gap-2 rounded-xl bg-warn-soft px-3 py-2 text-sm leading-5 text-warn">
          <AlertIcon width={16} height={16} className="mt-0.5 shrink-0" />
          <span><span className="font-semibold">{t("flags.label")}: </span>{t(flagWords(flag))}</span>
        </li>
      ))}
    </ul>
  );
}
