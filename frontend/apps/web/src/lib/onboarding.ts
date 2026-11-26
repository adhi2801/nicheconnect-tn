import type { components } from "@colyv/api";
import type { FieldError } from "./errors.ts";
import type { MessageKey } from "./app-messages.ts";

// A creator's first two steps (frontend/design/screen-plan.md C0). The rules mirror the backend's (POST /creators/me), so a field it
// would refuse is refused here first, in plain words. The backend stays the authority (frontend.md section 10).

export type Niche = components["schemas"]["CreatorProfileCreate"]["niches"][number];

/** In the contract's order. Ten niches; a creator picks one to five. */
export const NICHES: readonly Niche[] = ["food", "fashion", "beauty", "tech", "travel", "fitness", "education", "entertainment", "finance", "lifestyle"];
export const MAX_NICHES = 5;
export const NAME_MAX = 100;
export const CITY_MIN = 2;
export const CITY_MAX = 60;
const HANDLE = /^[a-z0-9._]{3,30}$/;

export type StepOne = { displayName: string; handle: string };
export type StepTwo = { city: string; niches: Niche[]; dateOfBirth: string };
export type Field = "displayName" | "handle" | "city" | "niches" | "dateOfBirth";
export type Problems = Partial<Record<Field, MessageKey>>;

/** As the backend stores it: trimmed, any leading @ dropped, lowercase. */
export const normalizeHandle = (raw: string): string => raw.trim().replace(/^@+/, "").toLowerCase();

/** Today's date in Tamil Nadu as YYYY-MM-DD. Only used to warn early; the backend decides the age with its own date. */
export function todayInIndia(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

/** 18 or over on `today` (both YYYY-MM-DD), compared as numbers (YYYYMMDD). Someone born on 29 February turns 18 on 1 March in a year
 *  without one, as the backend says: 29 February as a number falls between 28 February and 1 March, so no special case is needed. */
export function isAdult(bornOn: string, today: string): boolean {
  const [by, bm, bd] = bornOn.split("-").map(Number);
  const [ty, tm, td] = today.split("-").map(Number);
  return (by + 18) * 10_000 + bm * 100 + bd <= ty * 10_000 + tm * 100 + td;
}

const isRealDate = (value: string): boolean => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
};

export function checkStepOne({ displayName, handle }: StepOne): Problems {
  const problems: Problems = {};
  const name = displayName.trim();
  if (name.length === 0) problems.displayName = "onboarding.errors.nameMissing";
  else if (name.length > NAME_MAX) problems.displayName = "onboarding.errors.nameLong";
  const h = normalizeHandle(handle);
  if (h.length === 0) problems.handle = "onboarding.errors.handleMissing";
  else if (!HANDLE.test(h)) problems.handle = "onboarding.errors.handleShape";
  return problems;
}

export function checkStepTwo({ city, niches, dateOfBirth }: StepTwo, today: string): Problems {
  const problems: Problems = {};
  const c = city.trim();
  if (c.length < CITY_MIN) problems.city = "onboarding.errors.cityMissing";
  else if (c.length > CITY_MAX) problems.city = "onboarding.errors.cityLong";
  if (niches.length === 0) problems.niches = "onboarding.errors.nichesMissing";
  else if (niches.length > MAX_NICHES) problems.niches = "onboarding.errors.nichesTooMany";
  if (!dateOfBirth) problems.dateOfBirth = "onboarding.errors.dobMissing";
  else if (!isRealDate(dateOfBirth) || dateOfBirth > today) problems.dateOfBirth = "onboarding.errors.dobInvalid";
  else if (!isAdult(dateOfBirth, today)) problems.dateOfBirth = "onboarding.errors.underage";
  return problems;
}

/** Picking a niche toggles it; a sixth is not added (the picker says why). */
export function toggleNiche(chosen: readonly Niche[], niche: Niche): Niche[] {
  if (chosen.includes(niche)) return chosen.filter((n) => n !== niche);
  return chosen.length >= MAX_NICHES ? [...chosen] : [...chosen, niche];
}

/** The body for POST /creators/me. English is the only language today (D-054), sent as the contract asks. */
export function profileBody(one: StepOne, two: StepTwo): components["schemas"]["CreatorProfileCreate"] {
  return { display_name: one.displayName.trim(), handle: normalizeHandle(one.handle), city: two.city.trim(), niches: [...two.niches], languages: ["en"], date_of_birth: two.dateOfBirth };
}

const SERVER_FIELD: Record<string, Field> = { display_name: "displayName", handle: "handle", city: "city", niches: "niches", date_of_birth: "dateOfBirth" };
const GENERIC: Record<Field, MessageKey> = {
  displayName: "onboarding.errors.nameMissing",
  handle: "onboarding.errors.handleShape",
  city: "onboarding.errors.cityMissing",
  niches: "onboarding.errors.nichesMissing",
  dateOfBirth: "onboarding.errors.dobInvalid",
};

/** Where a refusal from the backend belongs, in our words. The backend's own message is never shown (it is written for developers). */
export function problemsFromServer(code: string | undefined, fields: FieldError[]): Problems {
  if (code === "handle_taken") return { handle: "onboarding.errors.handleTaken" };
  if (code === "must_be_18_or_over") return { dateOfBirth: "onboarding.errors.underage" };
  const problems: Problems = {};
  for (const { field } of fields) {
    const ours = SERVER_FIELD[field];
    if (ours && !problems[ours]) problems[ours] = GENERIC[ours];
  }
  return problems;
}

/** Which step holds the first problem, so a refusal from the backend takes the person back to the field. */
export const stepOf = (problems: Problems): 1 | 2 => (problems.displayName || problems.handle ? 1 : 2);
