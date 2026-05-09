/**
 * StatusFooter — composer-style ledger strip.
 * A tight, horizontal hairline-bound bar showing system state and
 * machine-readable build metadata. Sits at the bottom of every screen.
 */
export function StatusFooter() {
  const items: Array<{ label: string; value: string; color?: string }> = [
    { label: "Build",   value: "v0.1.0-alpha · a8c1f9" },
    { label: "Engine",  value: "Python 3.12 · ready" },
    { label: "Broker",  value: "Alpaca paper · OK", color: "#1FB85A" },
    { label: "Sync",    value: "12s ago" },
    { label: "Tz",      value: "America/New_York" },
  ];
  return (
    <footer
      className="px-6 py-2.5 flex items-center gap-5 hairline-t"
      style={{ background: "var(--paper-2)" }}
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden
          className="block-green inline-block"
          style={{ width: 7, height: 7, borderRadius: 2 }}
        />
        <span className="t-caption ink-muted">SYSTEM · GREEN</span>
      </div>
      <div className="hairline-l h-3" />
      {items.map((it, i) => (
        <div key={it.label} className="flex items-center gap-2">
          <span className="t-caption ink-subtle">{it.label}</span>
          <span
            className="t-mono"
            style={{ color: it.color ?? "var(--ink)", fontWeight: 600 }}
          >
            {it.value}
          </span>
          {i < items.length - 1 && <span className="ink-subtle">·</span>}
        </div>
      ))}
      <div className="ml-auto t-caption ink-subtle">
        <span className="t-mono">file-first source of truth</span>
      </div>
    </footer>
  );
}
