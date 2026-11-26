import { AlertIcon, ShieldIcon } from "@/components/ui/icons";
import { domainFacts, type Campaign } from "@/lib/campaigns";
import { formatDate, indiaDay } from "@/lib/format";
import { t } from "@/lib/app-messages";
import { todayInIndia } from "@/lib/onboarding";

/**
 * A brand's verified website as what was checked (legal.md section 3, item 74): the domain, since when, and when the registry says it
 * was registered; a recent registration said plainly, because a domain registered days ago is what scams use. Never "verified brand".
 * Ink words, green only on the shield: small green text on these surfaces falls below the 7:1 body-text bar.
 */
export function DomainLine({ domain, compact = false }: { domain: NonNullable<Campaign["verified_domain"]>; compact?: boolean }) {
  const facts = domainFacts(domain, todayInIndia(), indiaDay);
  const size = compact ? "text-xs" : "text-sm";
  return (
    <div className={`grid gap-1 ${size}`}>
      <p className="inline-flex items-start gap-1.5 font-semibold">
        <ShieldIcon width={compact ? 14 : 16} height={compact ? 14 : 16} aria-hidden className="mt-px shrink-0 text-ok" />
        {t("domain.verified", { domain: facts.domain, date: formatDate(facts.verifiedSince) })}
      </p>
      {!compact && facts.registeredOn && <p className="text-muted">{t("domain.registered", { date: formatDate(facts.registeredOn) })}</p>}
      {facts.recent && facts.registeredOn && (
        <p className="inline-flex items-start gap-1.5 rounded-lg bg-warn-soft px-2 py-1 font-semibold text-warn">
          <AlertIcon width={14} height={14} aria-hidden className="mt-px shrink-0" />
          {t("domain.recent", { date: formatDate(facts.registeredOn) })}
        </p>
      )}
    </div>
  );
}
