"use client";

import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import type { HourRow, Summary } from "@/lib/api";
import { CATEGORIAS, catColor, catLabel, cn, fmtInt, fmtPct } from "@/lib/utils";

const CURTO: Record<string, string> = {
  EM_NEGOCIACAO: "Negociação",
  NAO_E_O_CLIENTE: "Não é cliente",
  SEM_INTERESSE: "Sem interesse",
  LIGACAO_MUDA: "Muda",
  CAIXA_POSTAL: "Caixa postal",
  INDETERMINADO: "Indeterm.",
  PENDENTE: "Pendente",
};

/** Intensidade sequencial (um só tom, do claro ao escuro) misturada com a superfície: some no zero nos dois temas. */
const seq = (t: number) => `color-mix(in oklab, var(--seq) ${Math.round(8 + t * 84)}%, var(--chart-surface))`;
const inkOn = (t: number) => (t > 0.55 ? "#ffffff" : "rgb(var(--ink))");

// ---------------------------------------------------------------- Mapa de calor: hora × categoria
export function HourHeatmap({ data }: { data: HourRow[] }) {
  const [hover, setHover] = useState<{ h: number; c: string } | null>(null);
  const horas = data.filter((r) => CATEGORIAS.some((c) => r[c])).map((r) => r.hora);
  if (!horas.length) return null;
  const min = Math.min(...horas);
  const max = Math.max(...horas);
  const cols = data.filter((r) => r.hora >= min && r.hora <= max);
  const cats = CATEGORIAS.filter((c) => cols.some((r) => r[c]));
  const peak = Math.max(1, ...cols.flatMap((r) => cats.map((c) => r[c] || 0)));
  const hv = hover ? cols.find((r) => r.hora === hover.h)?.[hover.c] ?? 0 : 0;

  return (
    <div className="flex flex-col gap-3">
      <div className="scroll-thin overflow-x-auto">
        <div className="grid min-w-[520px] gap-[2px]" style={{ gridTemplateColumns: `128px repeat(${cols.length}, minmax(22px, 1fr))` }}>
          <div />
          {cols.map((r) => (
            <div key={r.hora} className="num pb-1 text-center text-[10px] text-ink-muted">
              {r.hora}h
            </div>
          ))}
          {cats.map((c) => (
            <Row key={c}>
              <div className="flex items-center gap-1.5 pr-2 text-xs text-ink-2">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: catColor(c) }} />
                <span className="truncate">{catLabel(c)}</span>
              </div>
              {cols.map((r) => {
                const v = r[c] || 0;
                const t = v / peak;
                const isH = hover?.h === r.hora && hover?.c === c;
                return (
                  <div
                    key={r.hora}
                    onMouseEnter={() => setHover({ h: r.hora, c })}
                    onMouseLeave={() => setHover(null)}
                    className={cn("num grid h-8 place-items-center rounded-[4px] text-[10px] transition", isH && "ring-2 ring-ink/60")}
                    style={{ background: v ? seq(t) : "rgb(var(--raised))", color: inkOn(t) }}
                    title={`${catLabel(c)} às ${r.hora}h: ${v}`}
                  >
                    {t > 0.5 ? v : ""}
                  </div>
                );
              })}
            </Row>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-muted">
        <span className="min-h-[16px]">
          {hover ? (
            <>
              <b className="font-medium text-ink">{catLabel(hover.c)}</b> às {hover.h}h: <span className="num">{fmtInt(hv)}</span> ligações
            </>
          ) : (
            "Passe o mouse para ver os valores"
          )}
        </span>
        <span className="flex items-center gap-1.5">
          menos
          {[0.05, 0.3, 0.55, 0.8, 1].map((t) => (
            <span key={t} className="h-2.5 w-4 rounded-[3px]" style={{ background: seq(t) }} />
          ))}
          mais
        </span>
      </div>
    </div>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

// ---------------------------------------------------------------- Matriz: tabulação do operador × categoria IA
export function ContrastMatrix({ data, onPick }: { data: Summary["matriz_contraste"]; onPick?: (tab: string) => void }) {
  // "Pendente" (ainda sem análise da IA) não entra na comparação; aparece só no total da linha
  const cats: string[] = CATEGORIAS.filter((c) => data.some((r) => r.categorias[c]));
  const diverge = (esperada: string, cat: string) => {
    // Indeterminado nunca acusa o operador: vai para revisão humana
    if (cat === "PENDENTE" || cat === "INDETERMINADO" || ["OUTRO"].includes(esperada)) return false;
    if (esperada === "MUDA_OU_CAIXA") return !["LIGACAO_MUDA", "CAIXA_POSTAL"].includes(cat);
    if (esperada === "NAO_TABULADO") return ["EM_NEGOCIACAO", "SEM_INTERESSE", "NAO_E_O_CLIENTE"].includes(cat);
    return esperada !== cat;
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="scroll-thin overflow-x-auto">
        <table className="w-full min-w-[600px] border-separate border-spacing-[2px] text-xs">
          <thead>
            <tr className="text-ink-2">
              <th className="sticky left-0 z-10 bg-surface pb-2 pr-3 text-left align-bottom font-medium">
                Operador tabulou <span className="text-ink-muted">→ IA ouviu</span>
              </th>
              {cats.map((c) => (
                <th key={c} className="w-[11%] pb-2 text-center align-bottom font-medium" title={catLabel(c)}>
                  <span className="mx-auto mb-1 block h-2 w-2 rounded-full" style={{ background: c === "PENDENTE" ? "var(--series-neutral)" : catColor(c) }} />
                  <span className="whitespace-nowrap">{CURTO[c] ?? catLabel(c)}</span>
                </th>
              ))}
              <th className="pb-2 pl-2 text-right font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => {
              const qualificadas = cats.filter((c) => c !== "PENDENTE").reduce((s, c) => s + (r.categorias[c] || 0), 0);
              return (
                <tr key={r.tabulacao_operador} className="group">
                  <td className="sticky left-0 z-10 max-w-[150px] bg-surface pr-3 sm:max-w-[240px]">
                    <button
                      onClick={() => onPick?.(r.tabulacao_operador)}
                      className="block w-full truncate py-1 text-left text-ink hover:underline"
                      title={r.tabulacao_operador}
                    >
                      {r.tabulacao_operador}
                    </button>
                  </td>
                  {cats.map((c) => {
                    const v = r.categorias[c] || 0;
                    const share = qualificadas && c !== "PENDENTE" ? v / qualificadas : 0;
                    const div = v > 0 && diverge(r.esperada, c);
                    return (
                      <td
                        key={c}
                        className={cn("num relative h-9 rounded-[4px] text-center transition", div && "ring-2 ring-inset ring-critical")}
                        style={{ background: v ? (c === "PENDENTE" ? "rgb(var(--raised))" : seq(share)) : "transparent", color: inkOn(share) }}
                        title={`${r.tabulacao_operador} → IA: ${catLabel(c)} = ${v}${qualificadas && c !== "PENDENTE" ? ` (${fmtPct(share * 100)})` : ""}${div ? " · divergente" : ""}`}
                      >
                        {v ? fmtInt(v) : <span className="text-ink-muted/50">·</span>}
                      </td>
                    );
                  })}
                  <td
                    className="num pl-2 text-right font-medium text-ink"
                    title={r.categorias.PENDENTE ? `${r.categorias.PENDENTE} ainda sem análise da IA` : undefined}
                  >
                    {fmtInt(r.total)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="flex items-center gap-1.5 text-[11px] text-ink-muted">
        <AlertTriangle className="h-3.5 w-3.5 text-critical" />
        Contorno vermelho = a IA discorda do que o operador tabulou (casos com pouca confiança vão para revisão, não entram aqui). Intensidade = participação na linha.
      </p>
    </div>
  );
}
