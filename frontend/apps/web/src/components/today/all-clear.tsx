import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t } from "@/lib/messages";
import type { Role } from "@/lib/session";
import { Kolam } from "./kolam";

/** Nothing waits on the person. Said calmly, with one way forward. */
export function AllClear({ role }: { role: Role }) {
  return (
    <Card className="grid justify-items-start gap-5 p-6 sm:p-8">
      <Kolam />
      <div className="grid gap-2">
        <h2 className="font-display text-2xl font-semibold tracking-tight">{t("today.allClear.title")}</h2>
        <p className="max-w-[48ch] text-[15px] leading-6 text-muted">{t(`today.allClear.body.${role}`)}</p>
      </div>
      <ButtonLink href={role === "creator" ? "/app/discover" : "/app/campaigns"}>{t(role === "creator" ? "today.allClear.ctaCreator" : "today.allClear.ctaBrand")}</ButtonLink>
    </Card>
  );
}
