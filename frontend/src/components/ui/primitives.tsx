"use client";

import { motion } from "framer-motion";
import { ChevronDown, Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import { cn, catColor, catLabel } from "@/lib/utils";

// ---------------------------------------------------------------- Button
type Variant = "primary" | "ghost" | "outline" | "danger" | "soft";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-ink text-surface hover:bg-ink/85 shadow-sm",
  soft: "bg-brand-soft text-brand-ink hover:bg-brand/15",
  outline: "border border-line bg-surface text-ink hover:bg-raised",
  ghost: "text-ink-2 hover:bg-raised hover:text-ink",
  danger: "bg-critical text-white hover:bg-critical/90",
};

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "icon"; loading?: boolean }
>(function Button({ className, variant = "outline", size = "md", loading, children, disabled, ...p }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-xl font-medium transition-all active:scale-[.97] disabled:pointer-events-none disabled:opacity-50",
        size === "sm" && "h-8 px-3 text-xs",
        size === "md" && "h-9 px-3.5 text-sm",
        size === "icon" && "h-9 w-9",
        VARIANTS[variant],
        className,
      )}
      {...p}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
});

// ---------------------------------------------------------------- Select
export function Select({
  label,
  className,
  children,
  ...p
}: SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  return (
    <label className={cn("relative block min-w-0", className)}>
      {label && <span className="mb-1 block text-[11px] font-medium text-ink-muted">{label}</span>}
      <select
        className={cn(
          "h-9 w-full appearance-none truncate rounded-xl border border-line bg-surface pl-3 pr-8 text-sm text-ink outline-none transition hover:border-ink/20 focus:border-brand",
          p.value ? "border-brand/40 bg-brand-soft/40" : "",
        )}
        {...p}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute bottom-2.5 right-2.5 h-4 w-4 text-ink-muted" />
    </label>
  );
}

// ---------------------------------------------------------------- Card
export function Card({
  title,
  subtitle,
  action,
  className,
  children,
  delay = 0,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
  delay?: number;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: [0.2, 0.7, 0.2, 1] }}
      className={cn("card flex min-w-0 flex-col p-4 sm:p-5", className)}
    >
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="card-sub mt-0.5">{subtitle}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </header>
      )}
      {children}
    </motion.section>
  );
}

// ---------------------------------------------------------------- Skeleton
export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn("relative overflow-hidden rounded-lg bg-raised", className)}>
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-ink/[.04] to-transparent" />
    </div>
  );
}

// ---------------------------------------------------------------- Badges
export function CategoryBadge({ code, sub, className }: { code?: string | null; sub?: string | null; className?: string }) {
  return (
    <span className={cn("inline-flex min-w-0 max-w-full items-center gap-1.5 text-xs font-medium text-ink", className)}>
      <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: catColor(code) }} aria-hidden />
      <span className="truncate">{catLabel(code)}</span>
      {sub && <span className="truncate font-normal text-ink-muted">· {sub}</span>}
    </span>
  );
}

export function Pill({ children, tone = "neutral", className }: { children: ReactNode; tone?: "neutral" | "brand" | "good" | "warn" | "critical"; className?: string }) {
  const tones = {
    neutral: "bg-raised text-ink-2",
    brand: "bg-brand-soft text-brand-ink",
    good: "bg-good/10 text-good",
    warn: "bg-warn/15 text-ink",
    critical: "bg-critical/10 text-critical",
  };
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", tones[tone], className)}>
      {children}
    </span>
  );
}

// ---------------------------------------------------------------- Empty
export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      {icon && <div className="grid h-11 w-11 place-items-center rounded-2xl bg-raised text-ink-muted">{icon}</div>}
      <p className="text-sm font-medium text-ink">{title}</p>
      {children && <div className="max-w-sm text-xs text-ink-muted">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- Meter (confiança)
export function Meter({ value, className }: { value?: number | null; className?: string }) {
  const v = Math.max(0, Math.min(1, value ?? 0));
  const tone = v >= 0.8 ? "bg-good" : v >= 0.6 ? "bg-warn" : "bg-critical";
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-raised">
        <motion.div
          className={cn("h-full rounded-full", tone)}
          initial={{ width: 0 }}
          animate={{ width: `${v * 100}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>
      <span className="num w-9 text-right text-xs text-ink-2">{value == null ? "–" : `${Math.round(v * 100)}%`}</span>
    </div>
  );
}
