import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t } from "@/lib/messages";

// Creating a campaign (screen-plan B3) is built after this page. Until then it answers kindly, as every unbuilt screen does.
export default function NewCampaignNotYet() {
  return (
    <Card className="mx-auto grid max-w-lg gap-4 p-8">
      <h1 className="font-display text-2xl font-semibold tracking-tight">{t("next.title")}</h1>
      <p className="text-[15px] leading-6 text-muted">{t("next.body")}</p>
      <ButtonLink href="/app" variant="secondary" className="justify-self-start">{t("next.back")}</ButtonLink>
    </Card>
  );
}
