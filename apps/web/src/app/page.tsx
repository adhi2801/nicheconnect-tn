// Foundation placeholder. The real entry decides between sign-in and the role's home (creator or brand).
export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-6 px-6">
      <p className="text-sm font-semibold uppercase tracking-widest text-muted">Colyv web</p>
      <h1 className="text-4xl font-semibold tracking-tight">One website. Creators and brands each see their own.</h1>
      <p className="text-lg text-muted">Foundation only: shared tokens, a typed API client, and the build. Screens come next.</p>
      <div className="rounded-xl border border-line bg-surface p-6">
        <p className="text-sm text-muted">Token check</p>
        <div className="mt-3 flex gap-3">
          <span className="rounded-lg bg-accent px-4 py-2 text-on-accent">Accent</span>
          <span className="rounded-lg px-4 py-2 text-ink" style={{ background: "linear-gradient(135deg, var(--c-glance-lime-from), var(--c-glance-lime-to))" }}>Lime</span>
          <span className="rounded-lg px-4 py-2 text-ink" style={{ background: "linear-gradient(135deg, var(--c-glance-coral-from), var(--c-glance-coral-to))" }}>Coral</span>
        </div>
      </div>
    </main>
  );
}
