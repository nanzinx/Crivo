"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Coffee, Gauge, ListMusic, PhoneCall } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from "recharts";
import { notaTone } from "@/components/avaliacao/calculo";
import { Card, Empty, Pill, Select, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn, fmtDateTime, fmtDay, fmtInt } from "@/lib/utils";

const fmtNota = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }));
const hhmm = (s: number | null | undefined) =>
  s == null ? "–" : `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}`;

export default function OperadorPage() {
  const { nome: bruto } = useParams<{ nome: string }>();
  const nome = decodeURIComponent(bruto);
  const [dias, setDias] = useState(30);
  const { data: r, error } = useQuery({ queryKey: ["operador", nome, dias], queryFn: () => api.operador(nome, dias) });

  if (error)
    return (
      <Card>
        <Empty title="Operador não encontrado">{(error as Error).message}</Empty>
      </Card>
    );

  return (
    <div className="space-y-5">
      <Link href="/supervisao" className="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink">
        <ArrowLeft className="h-3.5 w-3.5" /> Supervisão
      </Link>
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs text-ink-muted">{r?.equipe ?? "Equipe não identificada"}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{nome}</h1>
        </div>
        <div className="flex items-center gap-2">
          <Select aria-label="Período" value={String(dias)} onChange={(e) => setDias(Number(e.target.value))} className="w-40">
            {[7, 30, 90].map((d) => (
              <option key={d} value={d}>
                Últimos {d} dias
              </option>
            ))}
          </Select>
          <Link href={`/ligacoes?operador=${encodeURIComponent(nome)}`} className="inline-flex items-center gap-1 text-sm font-medium text-brand-ink hover:underline">
            <ListMusic className="h-4 w-4" /> Ligações
          </Link>
        </div>
      </header>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Kpi icon={<Gauge className="h-4 w-4" />} label="Nota média do script" valor={r ? fmtNota(r.monitoria.nota_media) : undefined} cls={notaTone(r?.monitoria.nota_media)} sub={r ? `${fmtInt(r.monitoria.avaliacoes)} avaliações` : undefined} />
        <Kpi icon={<AlertOctagon className="h-4 w-4" />} label="Falhas críticas" valor={r ? fmtInt(r.monitoria.falhas_criticas) : undefined} cls={r?.monitoria.falhas_criticas ? "text-critical" : undefined} />
        <Kpi icon={<PhoneCall className="h-4 w-4" />} label="Divergência de tabulação" valor={r ? `${r.ligacoes.taxa_divergencia.toLocaleString("pt-BR")}%` : undefined} sub={r ? `${fmtInt(r.ligacoes.divergencias)} de ${fmtInt(r.ligacoes.avaliadas)} avaliadas` : undefined} />
        <Kpi icon={<AlertTriangle className="h-4 w-4" />} label="Atrasos no ponto" valor={r ? fmtInt(r.ponto.atrasos) : undefined} sub={r ? `em ${r.ponto.dias.length} dia(s) importados` : undefined} cls={r?.ponto.atrasos ? "text-critical" : undefined} />
        <Kpi icon={<Coffee className="h-4 w-4" />} label="Almoço acima de 1h" valor={r ? fmtInt(r.ponto.almoco_acima_1h) : undefined} cls={r?.ponto.almoco_acima_1h ? "text-warn" : undefined} />
      </section>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card title="Nota do script por avaliação" subtitle="As 20 mais recentes · passe o mouse para ver cada uma" className="lg:col-span-3">
          {!r ? <Skeleton className="h-52" /> : r.monitoria.notas.length < 2 ? <Empty title="Poucas avaliações para o gráfico" /> : <Notas dados={r.monitoria.notas} />}
        </Card>
        <Card title="Trechos que mais erra" subtitle="Nas avaliações do período" className="lg:col-span-2">
          {!r ? (
            <Skeleton className="h-52" />
          ) : !r.monitoria.itens.length ? (
            <Empty icon={<CheckCircle2 className="h-5 w-5 text-good" />} title="Nenhum erro no período" />
          ) : (
            <ol className="space-y-2.5 text-xs">
              {r.monitoria.itens.map((it) => (
                <li key={it.texto}>
                  <div className="flex justify-between gap-2">
                    <span className="line-clamp-2 text-ink-2">{it.texto}</span>
                    <span className="num shrink-0 font-medium">{it.erro_pct.toLocaleString("pt-BR")}%</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-raised">
                    <div className="h-full rounded-full bg-[var(--series-1)]" style={{ width: `${Math.max(2, it.erro_pct)}%` }} />
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Ponto" subtitle="Últimos dias importados">
          {!r ? (
            <Skeleton className="h-40" />
          ) : !r.ponto.dias.length ? (
            <Empty title="Sem ponto importado para este operador" />
          ) : (
            <div className="-mx-4 overflow-x-auto sm:mx-0">
              <table className="w-full min-w-[460px] text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-[11px] uppercase tracking-wide text-ink-muted">
                    <th className="px-4 py-2 font-medium sm:px-0">Dia</th>
                    <th className="py-2 text-center font-medium">Entrada</th>
                    <th className="py-2 text-center font-medium">Saída</th>
                    <th className="py-2 text-center font-medium">Almoço</th>
                    <th className="py-2 text-center font-medium">QTP</th>
                    <th className="py-2 pr-4 font-medium sm:pr-0" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {r.ponto.dias.map((d) => (
                    <tr key={d.data} className={cn(d.atraso_min > 0 && "bg-critical/[.07]")}>
                      <td className="num px-4 py-2 sm:px-0">{fmtDay(d.data)}</td>
                      <td className="num py-2 text-center">{hhmm(d.entrada_seg)}</td>
                      <td className="num py-2 text-center">{d.completo ? hhmm(d.saida_seg) : "–"}</td>
                      <td className={cn("num py-2 text-center", (d.almoco_seg ?? 0) > 3600 && "font-semibold text-warn")}>{hhmm(d.almoco_seg)}</td>
                      <td className="num py-2 text-center">{d.qtp ?? "–"}</td>
                      <td className="py-2 pr-4 sm:pr-0">
                        {d.atraso_min > 0 && (
                          <Pill tone="critical">
                            <AlertTriangle className="h-3 w-3" /> {d.atraso_min} min
                          </Pill>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Avaliações e feedback" subtitle="As mais recentes">
          {!r ? (
            <Skeleton className="h-40" />
          ) : !r.monitoria.avaliacoes_recentes.length ? (
            <Empty title="Nenhuma avaliação do script no período" />
          ) : (
            <ul className="divide-y divide-line">
              {r.monitoria.avaliacoes_recentes.map((a) => (
                <li key={a.id}>
                  <Link href={`/monitoria/avaliar/${a.call_id}`} className="flex items-start gap-3 py-2.5 hover:bg-raised/40">
                    <span className={cn("num w-10 shrink-0 text-right text-lg font-semibold", notaTone(a.nota))}>{fmtNota(a.nota)}</span>
                    <div className="min-w-0 flex-1 text-xs">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="num text-ink-muted">{fmtDateTime(a.data_ligacao)}</span>
                        {a.falha_critica && <Pill tone="critical">falha crítica</Pill>}
                        {a.ciencia ? <Pill tone="good">ciência</Pill> : <Pill tone="warn">sem ciência</Pill>}
                      </div>
                      {a.feedback_melhorar && <p className="mt-0.5 line-clamp-2 text-ink-2">A melhorar: {a.feedback_melhorar}</p>}
                    </div>
                    <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-ink-muted" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function Kpi({ icon, label, valor, sub, cls }: { icon: React.ReactNode; label: string; valor?: string; sub?: string; cls?: string }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-1.5 text-xs text-ink-muted">
        {icon} {label}
      </div>
      {valor == null ? <Skeleton className="mt-2 h-7 w-16" /> : <div className={cn("num mt-1 text-2xl font-semibold tracking-tight", cls)}>{valor}</div>}
      {sub && <div className="mt-0.5 text-[11px] text-ink-muted">{sub}</div>}
    </div>
  );
}

function Tip({ active, payload }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as { data: string | null; nota: number | null; falha_critica: boolean };
  return (
    <div className="rounded-xl border border-line bg-surface p-3 text-xs shadow-pop">
      <div className="font-semibold text-ink">{fmtDateTime(d.data)}</div>
      <div className="text-ink-2">
        Nota <b className="num text-ink">{fmtNota(d.nota)}</b>
        {d.falha_critica && " · falha crítica"}
      </div>
    </div>
  );
}

function Notas({ dados }: { dados: { call_id: number; data: string | null; nota: number | null; falha_critica: boolean }[] }) {
  const pontos = dados.map((d, i) => ({ ...d, i: i + 1 }));
  return (
    <div className="h-52" role="img" aria-label={`Notas: ${pontos.map((d) => fmtNota(d.nota)).join(", ")}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={pontos} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis dataKey="i" tick={{ fill: "var(--chart-text)", fontSize: 11 }} axisLine={{ stroke: "var(--chart-axis)" }} tickLine={false} />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fill: "var(--chart-text)", fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip content={<Tip />} cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1 }} />
          <Line
            type="monotone"
            dataKey="nota"
            stroke="var(--series-1)"
            strokeWidth={2}
            dot={(p: { cx?: number; cy?: number; payload?: { falha_critica: boolean; call_id: number } }) => (
              <circle
                key={p.payload?.call_id}
                cx={p.cx}
                cy={p.cy}
                r={p.payload?.falha_critica ? 5 : 4}
                fill={p.payload?.falha_critica ? "rgb(var(--critical))" : "var(--series-1)"}
                stroke="var(--chart-surface)"
                strokeWidth={2}
              />
            )}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
