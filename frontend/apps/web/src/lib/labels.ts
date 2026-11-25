import { t } from "./messages";
import { NICHES, type Niche } from "./onboarding";

/** A niche's words. The contract types a campaign's niches as plain text, so one this app does not know yet shows as the backend sent it,
 *  never as a message key. */
export const nicheLabel = (niche: string): string => ((NICHES as readonly string[]).includes(niche) ? t(`niches.${niche as Niche}`) : niche);
