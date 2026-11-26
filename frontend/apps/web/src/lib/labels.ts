import type { MessageKey } from "./app-messages";
import { t } from "./app-messages";
import { NICHES, type Niche } from "./onboarding";

// Words for values the contract may grow. A value this app does not know yet shows as the backend sent it, never as a message key
// (a raw key such as "campaign.formats.carousel" would be shown otherwise).
const known = (key: string, table: Record<string, MessageKey>, raw: string): string => (key in table ? t(table[key]) : raw);

export const nicheLabel = (niche: string): string => ((NICHES as readonly string[]).includes(niche) ? t(`niches.${niche as Niche}`) : niche);

const TYPES: Record<string, MessageKey> = { paid: "campaignTypes.paid", barter: "campaignTypes.barter", commission: "campaignTypes.commission", local_business: "campaignTypes.local_business" };
export const campaignTypeLabel = (type: string): string => known(type, TYPES, type);

const FORMATS: Record<string, MessageKey> = { post: "campaign.formats.post", reel: "campaign.formats.reel", story: "campaign.formats.story", short: "campaign.formats.short", video: "campaign.formats.video", live: "campaign.formats.live", other: "campaign.formats.other" };
export const formatLabel = (format: string): string => known(format, FORMATS, format);

const PLATFORMS: Record<string, MessageKey> = { instagram: "campaign.platforms.instagram", youtube: "campaign.platforms.youtube" };
export const platformLabel = (platform: string): string => known(platform, PLATFORMS, platform);
