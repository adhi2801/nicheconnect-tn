"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { SelectField } from "@/components/ui/select-field";
import { TextField } from "@/components/ui/text-field";
import { activeFilterCount, CAMPAIGN_TYPES, type CampaignType, type Filters } from "@/lib/campaigns";
import { t } from "@/lib/messages";
import { NICHES, type Niche } from "@/lib/onboarding";

/** The four filters the API supports (GET /campaigns/discover): city, niche, type, minimum pay. Applied on submit, not per keystroke. */
export function DiscoverFilters({ value, cities, onApply }: { value: Filters; cities: string[]; onApply: (f: Filters) => void }) {
  const [city, setCity] = useState(value.city ?? "");
  const [niche, setNiche] = useState<string>(value.niche ?? "");
  const [type, setType] = useState<string>(value.type ?? "");
  const [min, setMin] = useState(value.minRupees ? String(value.minRupees) : "");
  const count = activeFilterCount(value);

  function submit(e: FormEvent) {
    e.preventDefault();
    const minRupees = Number(min.replace(/[₹,\s]/g, ""));
    onApply({
      city: city.trim().length >= 2 ? city.trim() : undefined,
      niche: (NICHES as readonly string[]).includes(niche) ? (niche as Niche) : undefined,
      type: (CAMPAIGN_TYPES as readonly string[]).includes(type) ? (type as CampaignType) : undefined,
      minRupees: Number.isInteger(minRupees) && minRupees > 0 ? minRupees : undefined,
    });
  }

  function clear() {
    setCity(""); setNiche(""); setType(""); setMin("");
    onApply({});
  }

  return (
    <form role="search" aria-label={t("discover.filters.label")} onSubmit={submit} className="grid gap-4 rounded-3xl bg-sunk p-4 sm:p-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <TextField label={t("discover.filters.city")} placeholder={t("discover.filters.cityPlaceholder")} value={city} onChange={(e) => setCity(e.target.value)} list="discover-cities" maxLength={60} />
        <datalist id="discover-cities">{cities.map((c) => <option key={c} value={c} />)}</datalist>
        <SelectField label={t("discover.filters.niche")} value={niche} onChange={(e) => setNiche(e.target.value)} options={[{ value: "", label: t("discover.filters.nicheAny") }, ...NICHES.map((n) => ({ value: n, label: t(`niches.${n}`) }))]} />
        <SelectField label={t("discover.filters.type")} value={type} onChange={(e) => setType(e.target.value)} options={[{ value: "", label: t("discover.filters.typeAny") }, ...CAMPAIGN_TYPES.map((c) => ({ value: c, label: t(`campaignTypes.${c}`) }))]} />
        <TextField label={t("discover.filters.min")} placeholder={t("discover.filters.minPlaceholder")} value={min} onChange={(e) => setMin(e.target.value)} inputMode="numeric" maxLength={12} />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" className="min-h-11">{t("discover.filters.show")}</Button>
        {count > 0 && <Button variant="quiet" className="min-h-11" onClick={clear}>{t("discover.filters.clear")}</Button>}
        {count > 0 && <p className="text-sm text-muted">{count === 1 ? t("discover.filters.activeOne") : t("discover.filters.active", { count })}</p>}
      </div>
    </form>
  );
}
