export type HeroTheme = "green" | "cyan" | "pink" | "orange" | "purple" | "ink";

const ACCENTS: Record<HeroTheme, { main: string; soft: string; text: string }> = {
  green:  { main: "#1FB85A", soft: "rgba(31,184,90,.10)", text: "#0F6B36" },
  cyan:   { main: "#1AC8E8", soft: "rgba(26,200,232,.12)", text: "#0E6E80" },
  pink:   { main: "#FF2D7A", soft: "rgba(255,45,122,.10)", text: "#A8164B" },
  orange: { main: "#F8A93B", soft: "rgba(248,169,59,.12)", text: "#8A4D10" },
  purple: { main: "#8B5CF6", soft: "rgba(139,92,246,.11)", text: "#4A2A9C" },
  ink:    { main: "#0A0A0A", soft: "rgba(10,10,10,.06)", text: "#0A0A0A" },
};

interface Props {
  theme?: HeroTheme;
  greeting: string;
  headline: string;
  meta?: string;
  stat?: { label: string; value: string; delta?: string };
}

export function Hero({ theme = "green", greeting, headline, meta, stat }: Props) {
  const accent = ACCENTS[theme];

  return (
    <section
      className="relative overflow-hidden"
      style={{
        background: "#FFFFFF",
        borderRadius: "var(--r-xl)",
        boxShadow: "var(--e2)",
        minHeight: 132,
      }}
    >
      <span
        aria-hidden
        className="absolute inset-y-0 left-0"
        style={{ width: 4, background: accent.main }}
      />
      <span
        aria-hidden
        className="absolute"
        style={{
          right: 18,
          top: 18,
          width: 42,
          height: 6,
          borderRadius: 2,
          background: accent.main,
          opacity: 0.95,
        }}
      />
      <div className="grid items-center gap-5 md:grid-cols-[minmax(0,1fr)_auto]" style={{ padding: "22px 24px 22px 28px" }}>
        <div className="min-w-0">
          <div className="t-caption ink-subtle">{greeting}</div>
          <h1
            className={`hero-headline hero-headline-${theme}`}
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 800,
              fontSize: "clamp(38px, 4.8vw, 72px)",
              lineHeight: 0.98,
              letterSpacing: "-0.048em",
              marginTop: 9,
              paddingBottom: "0.08em",
            }}
          >
            {headline}
          </h1>
          {meta && (
            <p
              className="t-body-md ink-muted"
              style={{ marginTop: 10, maxWidth: 720, lineHeight: 1.45 }}
            >
              {meta}
            </p>
          )}
        </div>

        {stat && (
          <div
            className="shrink-0"
            style={{
              minWidth: 220,
              maxWidth: 300,
              padding: "14px 16px",
              borderRadius: "var(--r-lg)",
              background: accent.soft,
              boxShadow: "inset 0 0 0 1px rgba(18,24,38,.07)",
            }}
          >
            <div className="t-caption" style={{ color: "rgba(42,51,66,.62)" }}>
              {stat.label}
            </div>
            <div
              className="t-num"
              style={{
                marginTop: 8,
                fontFamily: "var(--font-display)",
                fontWeight: 800,
                fontSize: 30,
                lineHeight: 1,
                letterSpacing: "-0.035em",
                color: accent.text,
                whiteSpace: "nowrap",
              }}
            >
              {stat.value}
            </div>
            {stat.delta && (
              <div className="t-body-sm" style={{ marginTop: 8, color: "var(--ink-muted)", fontWeight: 600 }}>
                {stat.delta}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
