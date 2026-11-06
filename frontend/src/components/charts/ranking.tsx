"use client";

import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, CircleAlert } from "lucide-react";
import { useState } from "react";
import type { Dist, Summary } from "@/lib/api";
import { DESLIG_LABEL, cn, fmtInt, fmtPct, initials } from "@/lib/utils";

const nivel = (t: number) =>
  t >= 20
    ? { cls: "bg-critical", icon: AlertTriangle, txt: "text-critical", label: "alta" }
    : t >= 10
      ? { cls: "bg-warn", icon: CircleAlert, txt: "text-ink-2", label: "média" }
      : { cls: "bg-good", icon: CheckCircle2, txt: "text-good", label: "baixa" };

export function OperatorRanking({
  data,
  selected,
  onSelect,
}: {
  data: Summary["ranking_operadores"];
  selected?: string;
  onSelect: (op: string | undefined) => void;
}) {
  const [sort, setSort] = useState<"taxa" | "total">("taxa");
  const [all, setAll] = useState(false);
  const sorted = [...data].sort((a, b) => (sort === "taxa" ? b.taxa_divergencia - a.taxa_divergencia : b.total - a.total));
  const rows = all ? sorted : sorted.slice(0, 6);
  const max = Math.max(25, ...rows.map((r) => r.taxa_divergencia));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1 self-end rounded-lg bg-raised p-0.5 text-[11px]">
        {(["taxa", "total"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setSort(s)}
            className={cn("rounded-md px-2 py-1 font-medium text-ink-muted", sort === s && "bg-surface text-ink shadow-sm")}
          >
            {s === "taxa" ? "Maior divergência" : "Mais ligações"}
          </button>
        ))}
      </div>
      <ul className="flex flex-col gap-1">
        {rows.map((r, i) => {
          const n = nivel(r.taxa_divergencia);
          const Icon = n.icon;
          return (
            <motion.li key={r.operador} layout transition={{ type: "spring", stiffness: 400, damping: 36 }}>
              <button
                onClick={() => onSelect(selected === r.operador ? undefined : r.operador)}
                className={cn(
                  "grid w-full grid-cols-[28px_1fr_auto] items-center gap-3 rounded-xl px-2 py-2 text-left transition hover:bg-raised",
                  selected === r.operador && "bg-brand-soft",
                )}
              >
                <span className="grid h-7 w-7 place-items-center rounded-full bg-raised text-[10px] font-semibold text-ink-2">
                  {initials(r.operador)}
                </span>
                <span className="min-w-0">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-sm text-ink">{r.operador}</span>
                    <span className="num shrink-0 text-[11px] text-ink-muted">
                      {fmtInt(r.divergencias)}/{fmtInt(r.qualificadas)}
                    </span>
                  </span>
                  <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-raised">
                    <motion.span
                      className={cn("block h-full rounded-full", n.cls)}
                      initial={{ width: 0 }}
                      animate={{ width: `${(r.taxa_divergencia / max) * 100}%` }}
                      transition={{ duration: 0.6, delay: i * 0.03 }}
                    />
                  </span>
                </span>
                <span className={cn("num flex w-[68px] items-center justify-end gap-1 text-sm font-semibold", n.txt)} title={`Divergência ${n.label}`}>
                  <Icon className="h-3.5 w-3.5" />
                  {fmtPct(r.taxa_divergencia, 0)}
                </span>
              </button>
            </motion.li>
          );
        })}
      </ul>
      {sorted.length > 6 && (
        <button onClick={() => setAll((v) => !v)} className="self-start text-xs font-medium text-brand-ink hover:underline">
          {all ? "Mostrar menos" : `Ver todos os ${sorted.length} operadores`}
        </button>
      )}
      <p className="text-[11px] text-ink-muted">Divergências ÷ ligações qualificadas · ícone: baixa &lt;10%, média 10–20%, alta ≥20%</p>
    </div>
  );
}

// ---------------------------------------------------------------- Divisões simples (barra fina segmentada em tons neutros)
const NEUTRAL = ["rgb(var(--ink) / .85)", "rgb(var(--ink) / .45)", "rgb(var(--ink) / .2)", "rgb(var(--ink) / .1)"];

export function SplitBar({ title, data, labels }: { title: string; data: Dist[]; labels?: Record<string, string> }) {
  if (!data.length) {
    return (
      <div>
        <div className="mb-2 text-xs font-medium text-ink-2">{title}</div>
        <div className="text-xs text-ink-muted">Sem dados — importe o relatório da discadora.</div>
      </div>
    );
  }
  return (
    <div>
      <div className="mb-2 text-xs font-medium text-ink-2">{title}</div>
      <div className="flex h-2 gap-[2px]">
        {data.map((d, i) => (
          <motion.span
            key={d.tipo}
            className="rounded-full"
            style={{ background: NEUTRAL[Math.min(i, NEUTRAL.length - 1)] }}
            initial={{ flexGrow: 0 }}
            animate={{ flexGrow: d.total }}
            transition={{ duration: 0.6 }}
            title={`${labels?.[d.tipo] ?? d.tipo}: ${fmtPct(d.pct)}`}
          />
        ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {data.map((d, i) => (
          <li key={d.tipo} className="flex items-center gap-1.5 text-xs text-ink-2">
            <span className="h-2 w-2 rounded-full" style={{ background: NEUTRAL[Math.min(i, NEUTRAL.length - 1)] }} />
            <span className="max-w-[160px] truncate">{labels?.[d.tipo] ?? titleCase(d.tipo)}</span>
            <span className="num font-medium text-ink">{fmtPct(d.pct, 0)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const titleCase = (s: string) => (s.length <= 4 ? s : s.charAt(0) + s.slice(1).toLowerCase());

export const DESLIG = DESLIG_LABEL;
