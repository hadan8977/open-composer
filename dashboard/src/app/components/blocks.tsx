import { ReactNode } from "react";

/* ---------------- Card ----------------
   Composer's surfaces are flat with hairline borders + faint contact
   shadow. Variants:
   - default  → white with hairline + e2 (sits on paper)
   - flat     → lighter elevation for nested surfaces
   - paper    → paper-3 surface for subtle nesting
   - dark     → black panel for charts/equity
*/

export function Card({
  children,
  className = "",
  pad = true,
  variant = "default",
}: {
  children: ReactNode;
  className?: string;
  pad?: boolean;
  variant?: "default" | "flat" | "paper" | "dark";
}) {
  const v =
    variant === "dark" ? "dscard-dark"
    : variant === "flat" ? "dscard-flat"
    : variant === "paper" ? "dscard-paper"
    : "dscard";
  return (
    <div className={`${v} ${pad ? "p-5" : ""} ${className}`}>{children}</div>
  );
}

export function SectionTitle({
  children,
  hint,
  action,
  tick,
}: {
  children: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
  /** Composer-style coloured tick prefix — marks a section opener */
  tick?: "green" | "pink" | "cyan" | "orange" | "purple" | "ink";
}) {
  const tickColors: Record<string, string> = {
    green: "#1FB85A", pink: "#FF2D7A", cyan: "#1AC8E8",
    orange: "#F8A93B", purple: "#8B5CF6", ink: "#0A0A0A",
  };
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0 flex items-center gap-2.5">
        {tick && (
          <span
            aria-hidden
            className="inline-block shrink-0"
            style={{ width: 8, height: 8, background: tickColors[tick], borderRadius: 2 }}
          />
        )}
        <div className="min-w-0">
          <div className="t-title-md ink truncate">{children}</div>
          {hint && <div className="t-body-sm ink-subtle mt-0.5">{hint}</div>}
        </div>
      </div>
      {action}
    </div>
  );
}

/* ---------------- Tag — sharp rectangle, bold, composer-style ---------------- */

const tagColors: Record<string, string> = {
  green:  "bg-[#1FB85A] text-[#042513]",
  pink:   "bg-[#FF2D7A] text-[#2C0414]",
  cyan:   "bg-[#1AC8E8] text-[#032730]",
  orange: "bg-[#F8A93B] text-[#2A1A05]",
  purple: "bg-[#8B5CF6] text-white",
  red:    "bg-[#EF4444] text-white",
  black:  "bg-[#0A0A0A] text-white",
  paper:  "bg-[#EEF2F7] text-[#0A0A0A]",
  white:  "bg-white text-[#0A0A0A]",
  ghost:  "bg-transparent text-[#5E6672] border border-[rgba(18,24,38,.18)]",
};

export function Tag({
  color = "paper",
  pill = false,
  children,
}: {
  color?: keyof typeof tagColors;
  pill?: boolean;
  children: ReactNode;
}) {
  return (
    <span className={`tag ${pill ? "tag-pill" : ""} ${tagColors[color]}`}>
      {children}
    </span>
  );
}

/* ---------------- Pill button ---------------- */

export function Pill({
  children,
  variant = "secondary",
  className = "",
  onClick,
}: {
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost";
  className?: string;
  onClick?: () => void;
}) {
  const v =
    variant === "primary" ? "pill-primary" : variant === "ghost" ? "pill-ghost" : "pill-secondary";
  return (
    <button onClick={onClick} className={`pill ${v} ${className}`}>
      {children}
    </button>
  );
}

/* ---------------- KPI block — composer tile, optional halftone ----------------
   The KPI is the workhorse coloured "tile" of the dashboard. Sharp corners,
   solid fill, bold black ink, optional halftone overprint.
*/

const blockClass: Record<string, string> = {
  black:  "block-black",
  green:  "block-green",
  pink:   "block-pink",
  cyan:   "block-cyan",
  orange: "block-orange",
  purple: "block-purple",
  yellow: "block-yellow",
  paper:  "block-paper",
};

const accentHex: Record<string, string> = {
  black:  "#0A0A0A",
  green:  "#1FB85A",
  pink:   "#FF2D7A",
  cyan:   "#1AC8E8",
  orange: "#F8A93B",
  purple: "#8B5CF6",
  yellow: "#F4D35E",
  paper:  "#8A93A0",
};

/**
 * KPI — composer-faithful: defaults to a neutral white surface with a
 * thin coloured top stripe, value rendered in ink (or theme accent),
 * delta in muted ink. Use `tile={true}` to opt into the bright filled
 * variant — reserve that for at most one hero-tier KPI per page.
 *
 * Value sizing is fluid via clamp() so long numbers like
 * "$112,481.20" never truncate inside narrow grid cells.
 */
export function KPI({
  label,
  value,
  delta,
  accent = "black",
  gradient,
  halftone = false,
  tile = false,
  valueColor,
}: {
  label: string;
  value: string;
  delta?: string;
  accent?: keyof typeof blockClass;
  gradient?: "green-cyan" | "pink-orange" | "ink-cyan";
  halftone?: boolean;
  /** Bright filled variant — composer's "lead" tile. Use sparingly. */
  tile?: boolean;
  /** Override the value colour on neutral KPIs (e.g. red P&L). */
  valueColor?: string;
}) {
  const gradClass =
    gradient === "green-cyan" ? "grad-green-cyan"
    : gradient === "pink-orange" ? "grad-pink-orange"
    : gradient === "ink-cyan" ? "grad-ink-cyan"
    : "";

  if (tile) {
    return (
      <div
        className={`relative ${blockClass[accent]} ${halftone ? "tile-halftone" : ""}`}
        style={{
          borderRadius: "var(--r-md)",
          padding: "14px 16px 16px",
          boxShadow: "0 0 0 1px rgba(10,10,10,.06), 0 1px 0 rgba(10,10,10,.05)",
          minHeight: 108,
          minWidth: 0,
        }}
      >
        <div className="t-caption" style={{ opacity: 0.78, position: "relative", zIndex: 1 }}>{label}</div>
        <div
          className={`t-num mt-2.5 ${gradClass}`}
          style={{
            position: "relative", zIndex: 1,
            fontFamily: "var(--font-display)",
            fontWeight: 800,
            fontSize: "clamp(22px, 2.4vw, 32px)",
            lineHeight: 1.04,
            letterSpacing: 0,
          }}
        >{value}</div>
        {delta && (
          <div
            className="t-body-sm mt-1.5"
            style={{ opacity: 0.78, fontWeight: 500, position: "relative", zIndex: 1 }}
          >{delta}</div>
        )}
      </div>
    );
  }

  // Default — paper-toned tonal card, accent corner stamp + accent value
  const stripe = accentHex[accent];
  const isInk = accent === "black";
  const valueHue = valueColor ?? (isInk ? "var(--ink)" : stripe);
  return (
    <div
      className="relative"
      style={{
        background: "linear-gradient(180deg, #FFFFFF 0%, #FAFCFF 100%)",
        borderRadius: "var(--r-md)",
        padding: "16px 18px 18px",
        boxShadow: "0 0 0 1px rgba(18,24,38,.08), 0 1px 0 rgba(18,24,38,.03)",
        minHeight: 116,
        minWidth: 0,
        overflow: "hidden",
      }}
    >
      {/* corner accent stamp */}
      <span
        aria-hidden
        className="absolute"
        style={{
          right: 12, top: 12,
          width: 14, height: 14,
          background: stripe,
          borderRadius: 2,
        }}
      />
      {/* tonal underline — accent fades horizontally */}
      <span
        aria-hidden
        className="absolute"
        style={{
          left: 0, right: 0, bottom: 0,
          height: 3,
          background: `linear-gradient(90deg, ${stripe} 0%, ${stripe}33 70%, transparent 100%)`,
        }}
      />
      <div
        className="t-caption"
        style={{ color: "rgba(42,51,66,.58)", letterSpacing: 0 }}
      >
        {label}
      </div>
      <div
        className={`t-num mt-2.5 ${gradClass}`}
        style={{
          color: gradClass ? undefined : valueHue,
          fontFamily: "var(--font-display)",
          fontWeight: 800,
          fontSize: "clamp(22px, 2.4vw, 32px)",
          lineHeight: 1.04,
          letterSpacing: 0,
        }}
      >{value}</div>
      {delta && (
        <div
          className="t-body-sm mt-1.5"
          style={{ color: "rgba(42,51,66,.62)", fontWeight: 500 }}
        >{delta}</div>
      )}
    </div>
  );
}

/* ---------------- Patterned color block (allocation, group covers) ---------------- */

export function ColorBlock({
  color,
  className = "",
  children,
  rounded = "md",
  halftone = false,
}: {
  color: keyof typeof blockClass | "paper";
  className?: string;
  children?: ReactNode;
  rounded?: "none" | "sm" | "md" | "lg";
  halftone?: boolean;
}) {
  const cls = color === "paper" ? "block-paper" : blockClass[color];
  const radius =
    rounded === "none" ? "0"
    : rounded === "lg" ? "var(--r-lg)"
    : rounded === "md" ? "var(--r-md)"
    : "var(--r-xs)";
  return (
    <div
      className={`relative ${cls} ${halftone ? "tile-halftone" : ""} ${className}`}
      style={{ borderRadius: radius }}
    >
      {children}
    </div>
  );
}
