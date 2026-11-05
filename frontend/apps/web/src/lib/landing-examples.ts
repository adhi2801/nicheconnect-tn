import type { BoardStage, Memo } from "./deals.ts";

// The landing page's example board (frontend.md: real product screens, never a picture of one). Three made-up deals, each a whole
// memo as the API sends it, so the cards are the app's own components fed the app's own shape; the page says they are examples.
// Every name here is invented for the page.

const base: Memo = {
  id: "00000000-0000-4000-8000-000000000000",
  application_id: "00000000-0000-4000-8000-000000000100",
  status: "accepted",
  stage: "agreed",
  waiting_on: "creator",
  campaign_title: "",
  counterparty_name: "",
  fee_amount_paise: null,
  agreed_amount_paise: null,
  currency: "INR",
  deliverables: "2 Instagram reels",
  deliverable_items: [],
  content_due_on: null,
  work_due_on: null,
  work_started_at: null,
  approval_window_days: 7,
  payment_due_days: 7,
  usage_rights_days: null,
  disclosure_required: true,
  draft_review: false,
  extra_terms: null,
  change_request_message: null,
  revision_count: 0,
  cancellation_kind: null,
  cancellation_fee_paise: 0,
  has_open_dispute: false,
  text_flags: [],
  created_at: "2026-11-01T09:00:00Z",
  updated_at: "2026-11-01T09:00:00Z",
  sent_at: "2026-11-01T09:00:00Z",
  accepted_at: "2026-11-02T09:00:00Z",
  declined_at: null,
  cancelled_at: null,
};

const example = (n: number, fields: Partial<Memo>): Memo => ({ ...base, id: `00000000-0000-4000-8000-00000000000${n}`, ...fields });

/** One deal per stage shown, in journey order: the creator's move, then the brand's, then done. */
export const EXAMPLE_BOARD: { stage: BoardStage; memo: Memo }[] = [
  {
    stage: "in_progress",
    memo: example(1, {
      stage: "in_progress",
      waiting_on: "creator",
      campaign_title: "Pongal millet laddu box",
      counterparty_name: "Kavi Kitchen",
      fee_amount_paise: 800_000,
      agreed_amount_paise: 800_000,
      content_due_on: "2027-01-10",
      work_started_at: "2026-11-03T09:00:00Z",
    }),
  },
  {
    stage: "payment",
    memo: example(2, {
      stage: "payment",
      waiting_on: "brand",
      campaign_title: "Silk saree festive drop",
      counterparty_name: "Vaigai Weaves",
      fee_amount_paise: 1_200_000,
      agreed_amount_paise: 1_200_000,
      content_due_on: "2026-11-20",
    }),
  },
  {
    stage: "finished",
    memo: example(3, {
      stage: "finished",
      waiting_on: null,
      campaign_title: "Margazhi season skincare",
      counterparty_name: "Nila Skincare",
      fee_amount_paise: 1_500_000,
      agreed_amount_paise: 1_500_000,
      content_due_on: "2026-11-15",
    }),
  },
];
