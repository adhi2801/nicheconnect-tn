"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ChoiceGroup } from "@/components/ui/choice-group";
import { CodeField } from "@/components/ui/code-field";
import { Notice } from "@/components/ui/notice";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { TextField } from "@/components/ui/text-field";

const swatches = ["ground", "surface", "surface-sunk", "ink", "ink-muted", "line-strong", "accent", "highlight", "highlight-soft", "ok", "ok-soft", "warn", "warn-soft", "bad", "bad-soft"];

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4"><h2 className="font-display text-xl font-semibold tracking-tight">{title}</h2>{children}</section>
  );
}

export function Catalogue() {
  const [code, setCode] = useState("42");
  const [role, setRole] = useState<"creator" | "brand">("creator");
  return (
    <main className="mx-auto grid w-full max-w-5xl gap-12 px-5 py-12">
      <header className="grid gap-2">
        <p className="text-sm font-semibold uppercase tracking-widest text-muted">Colyv web · components</p>
        <h1 className="font-display text-4xl font-semibold tracking-tight">Catalogue</h1>
        <p className="max-w-[65ch] text-muted">Every component in every state. A missing component is added here first, never made one-off inside a screen.</p>
      </header>

      <Block title="Colour">
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          {swatches.map((s) => (
            <div key={s} className="grid gap-1.5"><div className="h-14 rounded-2xl border border-line" style={{ background: `var(--c-${s})` }} /><span className="font-mono text-xs text-muted">{s}</span></div>
          ))}
        </div>
      </Block>

      <Block title="Type">
        <Card className="grid gap-2">
          <p className="font-display text-4xl font-semibold tracking-tight">Every deal, on the record</p>
          <p className="font-display text-2xl font-semibold tracking-tight">Display, Plus Jakarta Sans</p>
          <p className="text-[16px] leading-7">Body, Inter. Colyv records who marked a payment as sent and when, and who confirmed it arrived.</p>
          <p className="font-mono text-sm">₹1,50,000 · 17 Sep 2026 · mono, JetBrains Mono</p>
        </Card>
      </Block>

      <Block title="Button">
        <div className="flex flex-wrap items-center gap-3">
          <Button>Primary</Button><Button variant="secondary">Secondary</Button><Button variant="quiet">Quiet</Button>
          <Button disabled>Disabled</Button><Button loading>Sending code</Button>
        </div>
      </Block>

      <Block title="Pill: always a word and an icon">
        <div className="flex flex-wrap gap-2"><Pill tone="ok">Confirmed received</Pill><Pill tone="warn">Marked paid</Pill><Pill tone="bad">Late 3 days</Pill><Pill tone="neutral">Draft</Pill><Pill tone="dark">Needs you</Pill></div>
      </Block>

      <Block title="Text field">
        <div className="grid items-start gap-5 sm:grid-cols-3">
          <TextField label="Default" hint="A hint says why we ask." placeholder="Type here" />
          <TextField label="Filled" defaultValue="Lakshmi Loves" />
          <TextField label="Error" error="Enter a 10-digit Indian mobile number." defaultValue="12345" prefix="+91" />
          <TextField label="Disabled" disabled defaultValue="Not editable" />
        </div>
      </Block>

      <Block title="Code field">
        <div className="grid max-w-md gap-5">
          <CodeField label="Typing" value={code} onChange={setCode} />
          <CodeField label="Error" value="123456" onChange={() => undefined} error="That code is wrong, has expired or was already used." />
        </div>
      </Block>

      <Block title="Choice group">
        <ChoiceGroup legend="I am a" value={role} onChange={setRole} choices={[{ value: "creator", title: "Creator", hint: "Find campaigns, do the work, confirm you were paid." }, { value: "brand", title: "Brand", hint: "Post campaigns, choose creators, keep every deal on record." }]} />
      </Block>

      <Block title="Notice">
        <div className="grid gap-3"><Notice>Information that is not urgent.</Notice><Notice tone="error" action={<Button variant="secondary" className="min-h-10 px-4 text-sm">Try again</Button>}>Colyv is busy right now. Nothing was changed.</Notice></div>
      </Block>

      <Block title="Card and skeleton">
        <div className="grid items-start gap-4 sm:grid-cols-3">
          <Card className="grid gap-2"><p className="text-sm text-muted">Light card</p><p className="font-display text-3xl font-semibold tracking-tight">₹7,000</p></Card>
          <Card tone="dark" className="grid gap-2"><p className="text-sm opacity-80">Dark card, one per screen</p><p className="font-display text-3xl font-semibold tracking-tight">3 need you</p></Card>
          <Card className="grid gap-3" aria-busy="true"><Skeleton className="h-5 w-1/2" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-3/4" /></Card>
        </div>
      </Block>
    </main>
  );
}
