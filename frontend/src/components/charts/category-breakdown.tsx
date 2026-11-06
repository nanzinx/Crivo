"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import type { Summary } from "@/lib/api";
import { CATEGORIAS, catColor, catLabel, cn, fmtInt, fmtPct } from "@/lib/utils";

/** Barra segmentada (um todo dividido em partes) + lista com subcategorias expansíveis. */
export function CategoryBreakdown({
  data,
  selected,
  onSelect,
}: {
  data: Summary["categorias"];
  selected?: string;
  onSelect: (code: string | undefined) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const ordered = CATEGORIAS.map((c) => data.find((d) => d.codigo === c)).filter(Boolean) as Summary["categorias"];
  const total = ordered.reduce((s, c) => s + c.total, 0);

  return (
    <div className="flex flex-col gap-5">
      {/* barra alta segmentada: 28px, blocos com 2px de respiro */}
      <div className="flex h-7 w-full gap-[2px]" role="img" aria-label={ordered.map((c) => `${c.label}: ${fmtPct(c.pct)}`).join(", ")}>
        {ordered.map((c, i) => (
          <motion.button
            key={c.codigo}
            initial={{ flexGrow: 0 }}
            animate={{ flexGrow: c.total }}
            transition={{ duration: 0.7, delay: i * 0.05, ease: [0.2, 0.7, 0.2, 1] }}
            onMouseEnter={() => setHover(c.codigo)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(c.codigo)}
            onBlur={() => setHover(null)}
            onClick={() => onSelect(selected === c.codigo ? undefined : c.codigo)}
            className={cn(
              "relative min-w-[3px] basis-0 overflow-hidden rounded-[4px] text-left transition-opacity",
              (hover && hover !== c.codigo) || (selected && selected !== c.codigo) ? "opacity-35" : "opacity-100",
            )}
            style={{ background: catColor(c.codigo) }}
            aria-label={`${c.label}: ${fmtInt(c.total)} (${fmtPct(c.pct)})`}
          >
            {c.pct >= 8 && (
              <span
                className="num absolute inset-y-0 left-2 flex items-center text-[11px] font-semibold"
                style={{ color: c.codigo === "LIGACAO_MUDA" ? "#0b0b0b" : "#fff" }}
              >
                {Math.round(c.pct)}%
              </span>
            )}
          </motion.button>
        ))}
      </div>

      <ul className="divide-y divide-line">
        {ordered.map((c) => {
          const isOpen = open === c.codigo;
          return (
            <li key={c.codigo}>
              <div
                className={cn(
                  "flex items-center gap-3 rounded-lg py-2.5 transition-colors",
                  hover === c.codigo && "bg-raised/60",
                )}
                onMouseEnter={() => setHover(c.codigo)}
                onMouseLeave={() => setHover(null)}
              >
                <button
                  onClick={() => setOpen(isOpen ? null : c.codigo)}
                  className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-ink-muted hover:bg-raised"
                  aria-expanded={isOpen}
                  aria-label={`Subcategorias de ${c.label}`}
                >
                  <ChevronRight className={cn("h-4 w-4 transition-transform", isOpen && "rotate-90")} />
                </button>
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: catColor(c.codigo) }} />
                <button
                  onClick={() => onSelect(selected === c.codigo ? undefined : c.codigo)}
                  className={cn("min-w-0 flex-1 truncate text-left text-sm text-ink hover:underline", selected === c.codigo && "font-semibold")}
                >
                  {catLabel(c.codigo)}
                </button>
                <span className="num text-sm font-medium text-ink">{fmtInt(c.total)}</span>
                <span className="num w-14 text-right text-xs text-ink-muted">{fmtPct(c.pct)}</span>
              </div>
              <AnimatePresence initial={false}>
                {isOpen && (
                  <motion.ul
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden pb-2 pl-14 pr-1"
                  >
                    {c.subs.map((s) => {
                      const pct = c.total ? (s.total / c.total) * 100 : 0;
                      return (
                        <li key={s.codigo ?? "nd"} className="grid grid-cols-[1fr_auto] items-center gap-x-3 py-1">
                          <span className="truncate text-xs text-ink-2">{s.label}</span>
                          <span className="num text-xs text-ink-2">{fmtInt(s.total)}</span>
                          <div className="col-span-2 h-1 overflow-hidden rounded-full bg-raised">
                            <motion.div
                              className="h-full rounded-full"
                              style={{ background: catColor(c.codigo) }}
                              initial={{ width: 0 }}
                              animate={{ width: `${pct}%` }}
                              transition={{ duration: 0.5 }}
                            />
                          </div>
                        </li>
                      );
                    })}
                  </motion.ul>
                )}
              </AnimatePresence>
            </li>
          );
        })}
      </ul>
      <p className="text-[11px] text-ink-muted">{fmtInt(total)} ligações qualificadas · clique numa categoria para filtrar o painel</p>
    </div>
  );
}
