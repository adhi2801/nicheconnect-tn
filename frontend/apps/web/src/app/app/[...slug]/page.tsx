import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t } from "@/lib/messages";

// Every screen after Today answers here until it is built, so no link in the app ever ends in an error page.
export default function NextScreen() {
  return (
    <Card className="mx-auto grid max-w-lg gap-4 p-8">
      <h1 className="font-display text-2xl font-semibold tracking-tight">{t("next.title")}</h1>
      <p className="text-[15px] leading-6 text-muted">{t("next.body")}</p>
      <ButtonLink href="/app" variant="secondary" className="justify-self-start">{t("next.back")}</ButtonLink>
    </Card>
  );
}
