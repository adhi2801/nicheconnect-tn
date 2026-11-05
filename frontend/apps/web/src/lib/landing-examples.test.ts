import { strict as assert } from "node:assert";
import { test } from "node:test";
import { EXAMPLE_BOARD } from "./landing-examples.ts";
import { amountOf, moveOf } from "./deals.ts";

test("each example deal sits in the column of its own stage", () => {
  for (const { stage, memo } of EXAMPLE_BOARD) assert.equal(memo.stage, stage);
});

test("the board reads as a journey: the creator's move, the brand's, then done", () => {
  assert.deepEqual(
    EXAMPLE_BOARD.map(({ memo }) => moveOf(memo, "creator")),
    ["yours", "theirs", "ended"],
  );
});

test("every example has a fee to show, a name and a campaign, and its own id", () => {
  for (const { memo } of EXAMPLE_BOARD) {
    assert.ok((amountOf(memo) ?? 0) > 0);
    assert.ok(memo.counterparty_name && memo.campaign_title);
  }
  assert.equal(new Set(EXAMPLE_BOARD.map(({ memo }) => memo.id)).size, EXAMPLE_BOARD.length);
});
