// Indian formats, through Intl and never by hand (docs/standards/frontend.md section 7): ₹1,50,000 and 17 Sep 2026.
// The API sends money as whole paise and dates as Tamil Nadu calendar dates ("2026-10-28").

const rupees = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const rupeesAndPaise = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** 15000000 paise is ₹1,50,000. Paise are shown only when there are some. */
export function formatPaise(paise: number): string {
  return paise % 100 === 0 ? rupees.format(paise / 100) : rupeesAndPaise.format(paise / 100);
}

/** A calendar date has no time zone, so it is read as the same day everywhere. */
function calendarDate(isoDate: string): Date {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

const day = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const dayNoYear = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
const longDay = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });

// Intl's Indian English writes September as "Sept"; our style, and the standard's example, is "Sep".
const shorten = (text: string): string => text.replace(/\./g, "").replace("Sept", "Sep");

/** "17 Sep 2026" */
export const formatDate = (isoDate: string): string => shorten(day.format(calendarDate(isoDate)));

/** "17 Sep", for a date in the same year as the one beside it. */
export const formatDayMonth = (isoDate: string): string => shorten(dayNoYear.format(calendarDate(isoDate)));

/** "Wednesday 28 October" (the weekday and the date, in the order Indians say them). */
export function formatLongDate(isoDate: string): string {
  const parts = longDay.formatToParts(calendarDate(isoDate));
  const pick = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${pick("weekday")} ${pick("day")} ${pick("month")}`;
}

/** Morning, afternoon or evening in India. A greeting is not a deadline, so the device's clock is fine for it. */
export function partOfDay(now: Date = new Date()): "morning" | "afternoon" | "evening" {
  const hour = Number(new Intl.DateTimeFormat("en-IN", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }).format(now)) % 24;
  return hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
}

/** "Lakshmi Loves" gives "LL". Used where there is no photograph. */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const letters = words.length === 1 ? [...words[0]].slice(0, 2) : [[...words[0]][0], [...words[words.length - 1]][0]];
  return letters.join("").toUpperCase();
}
