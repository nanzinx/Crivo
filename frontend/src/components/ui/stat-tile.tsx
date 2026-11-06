"use client";

import { animate, motion, useMotionValue, useTransform } from "framer-motion";
import { useEffect, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Skeleton } from "./primitives";

export function AnimatedNumber({ value, format }: { value: number; format: (n: number) => string }) {
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => format(v));
  useEffect(() => {
    const c = animate(mv, value, { duration: 0.8, ease: [0.2, 0.7, 0.2, 1] });
    return c.stop;
  }, [mv, value]);
  return <motion.span>{text}</motion.span>;
}

export function StatTile({
  label,
  value,
  format,
  hint,
  icon,
  tone,
  loading,
  hero,
  onClick,
  active,
  delay = 0,
}: {
  label: string;
  value?: number | null;
  format: (n: number) => string;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: "critical" | "warn" | "good";
  loading?: boolean;
  hero?: boolean;
  onClick?: () => void;
  active?: boolean;
  delay?: number;
}) {
  const Comp = onClick ? motion.button : motion.div;
  return (
    <Comp
      type={onClick ? "button" : undefined}
      onClick={onClick}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay }}
      className={cn(
        "card group relative flex min-w-0 flex-col justify-between gap-3 overflow-hidden p-4 text-left transition",
        onClick && "cursor-pointer hover:border-ink/20 hover:shadow-pop/10",
        active && "border-brand ring-2 ring-brand/20",
        hero && "sm:col-span-2 lg:col-span-1",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-medium text-ink-2">{label}</span>
        {icon && (
          <span
            className={cn(
              "grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-raised text-ink-2",
              tone === "critical" && "bg-critical/10 text-critical",
              tone === "warn" && "bg-warn/15 text-ink",
              tone === "good" && "bg-good/10 text-good",
            )}
          >
            {icon}
          </span>
        )}
      </div>
      {loading || value == null ? (
        <Skeleton className={cn("h-8 w-24", hero && "h-12 w-32")} />
      ) : (
        <div className={cn("font-semibold tracking-tight text-ink", hero ? "text-4xl sm:text-5xl" : "text-2xl sm:text-[28px]")}>
          <AnimatedNumber value={value} format={format} />
        </div>
      )}
      {hint && <div className="min-h-[16px] truncate text-xs text-ink-muted">{hint}</div>}
    </Comp>
  );
}
