"use client";

import { BarChart3, Table2 } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from "recharts";
import type { TimelineRow } from "@/lib/api";
import { CATEGORIAS, catColor, catLabel, cn, fmtCompact, fmtDay, fmtInt } from "@/lib/utils";

export function Legend({ keys, className }: { keys: readonly string[]; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap gap-x-4 gap-y-1.5", className)}>
      {keys.map((k) => (
        <li key={k} className="flex items-center gap-1.5 text-xs text-ink-2">
          <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: catColor(k) }} />
          {catLabel(k)}
        </li>
      ))}
    </ul>
  );
}

function Tip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const rows = [...payload].filter((p) => p.value).reverse();
  const total = rows.reduce((s, p) => s + Number(p.value || 0), 0);
  return (
    <div className="min-w-[200px] rounded-xl border border-line bg-surface p-3 shadow-pop">
      <div className="mb-2 flex items-baseline justify-between gap-4">
        <span className="text-xs font-semibold text-ink">{fmtDay(String(label))}</span>
        <span className="num text-xs text-ink-muted">{fmtInt(total)} ligações</span>
      </div>
      <ul className="space-y-1">
        {rows.map((p) => (
          <li key={p.dataKey as string} className="flex items-center gap-2 text-xs">
            <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: catColor(p.dataKey as string) }} />
            <span className="flex-1 text-ink-2">{catLabel(p.dataKey as string)}</span>
            <span className="num font-medium text-ink">{fmtInt(Number(p.value))}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TimelineChart({ data }: { data: TimelineRow[] }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const keys = CATEGORIAS.filter((k) => data.some((d) => Number(d[k] || 0) > 0));
  const last = keys[keys.length - 1];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <Legend keys={keys} />
        <div className="flex shrink-0 rounded-lg bg-raised p-0.5">
          {(["chart", "table"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              aria-label={v === "chart" ? "Ver gráfico" : "Ver tabela"}
              className={cn("grid h-7 w-8 place-items-center rounded-md text-ink-muted", view === v && "bg-surface text-ink shadow-sm")}
            >
              {v === "chart" ? <BarChart3 className="h-4 w-4" /> : <Table2 className="h-4 w-4" />}
            </button>
          ))}
        </div>
      </div>

      {view === "chart" ? (
        <div className="h-[260px] w-full sm:h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 4, left: -12, bottom: 0 }} barCategoryGap="22%">
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis
                dataKey="data"
                tickFormatter={fmtDay}
                tickLine={false}
                axisLine={{ stroke: "var(--chart-axis)" }}
                tick={{ fill: "var(--chart-text)", fontSize: 11 }}
                minTickGap={16}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tick={{ fill: "var(--chart-text)", fontSize: 11 }}
                tickFormatter={fmtCompact}
                allowDecimals={false}
                width={44}
              />
              <Tooltip content={<Tip />} cursor={{ fill: "rgb(var(--ink) / 0.04)" }} />
              {keys.map((k) => (
                <Bar
                  key={k}
                  dataKey={k}
                  stackId="a"
                  fill={catColor(k)}
                  stroke="var(--chart-surface)"
                  strokeWidth={2}
                  maxBarSize={24}
                  radius={k === last ? [4, 4, 0, 0] : 0}
                  animationDuration={700}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="scroll-thin max-h-[300px] overflow-auto rounded-xl border border-line">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-raised text-ink-2">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Dia</th>
                {keys.map((k) => (
                  <th key={k} className="px-3 py-2 text-right font-medium">
                    {catLabel(k)}
                  </th>
                ))}
                <th className="px-3 py-2 text-right font-medium">Total</th>
              </tr>
            </thead>
            <tbody className="num divide-y divide-line">
              {data.map((d) => (
                <tr key={d.data}>
                  <td className="px-3 py-1.5 text-ink-2">{fmtDay(d.data)}</td>
                  {keys.map((k) => (
                    <td key={k} className="px-3 py-1.5 text-right">
                      {fmtInt(Number(d[k] || 0))}
                    </td>
                  ))}
                  <td className="px-3 py-1.5 text-right font-medium">{fmtInt(keys.reduce((s, k) => s + Number(d[k] || 0), 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
