import type { components } from "@colyv/api";
import type { MessageKey } from "./app-messages.ts";

// Report and block, one tap from anything another person sent (trust-and-safety.md section 5). The backend decides everything: who
// may report what, the limit of 10 an hour, and that a block is never told to the other side (POST /reports, POST /me/blocks).

export type ReportCategory = components["schemas"]["ReportCreate"]["category"];
export type Subject = { kind: components["schemas"]["ReportCreate"]["subject_kind"]; id: string };

/** In the order a creator is most likely to need them. Every category the contract has is offered. */
export const REPORT_CATEGORIES: readonly ReportCategory[] = ["spam", "fake_profile", "non_payment", "abuse", "impersonation", "intimate_content", "other"];
export const REPORT_NOTE_MAX = 1000;

/** How soon a report is looked at, as the backend promises it (ReportCreate.category, item 51). */
export function answeredWithin(category: ReportCategory): MessageKey {
  if (category === "impersonation" || category === "intimate_content") return "safety.report.within2h";
  if (category === "non_payment") return "safety.report.within7d";
  return "safety.report.within36h";
}

export function reportBody(subject: Subject, category: ReportCategory, note: string): components["schemas"]["ReportCreate"] {
  const trimmed = note.trim();
  return { subject_kind: subject.kind, subject_id: subject.id, category, note: trimmed ? trimmed : null };
}

/** The note is optional; when given it is at most 1,000 characters, counted as the backend counts them. */
export const noteTooLong = (note: string): boolean => [...note.trim()].length > REPORT_NOTE_MAX;
