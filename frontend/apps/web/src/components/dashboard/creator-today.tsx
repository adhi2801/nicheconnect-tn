"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { DesignSlot } from "@/design/design-slot";
import { NeedsYouArea, type Attention } from "@/components/today/needs-you-area";
import { PaymentGauge } from "@/components/today/payment-gauge";
import { ApplicationsPanel } from "./applications-panel";
import { ComingUp } from "./coming-up";
import { NextDue } from "./next-due";

/** A creator's Today: what needs them, their applications, what is due, what is coming up, and where their payments stand. */
export function CreatorToday({ attention }: { attention: UseQueryResult<Attention> }) {
  const items = attention.data?.items ?? [];
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <div className="grid gap-4">
        <NeedsYouArea attention={attention} role="creator" />
        <ApplicationsPanel />
      </div>
      <div className="grid gap-4">
        <DesignSlot id="today.feature" optional className="rounded-[2rem]" />
        <NextDue items={items} role="creator" />
        <ComingUp role="creator" />
        <PaymentGauge role="creator" />
      </div>
    </div>
  );
}
