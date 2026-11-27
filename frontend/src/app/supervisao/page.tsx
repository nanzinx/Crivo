"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, ArrowRight, CheckCircle2, ClipboardList, Download, Eye, Gauge, Users } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipProps } from "recharts";
import { notaTone } from "@/components/avaliacao/calculo";
import { Button, Card, Empty, Pill, Select, Skeleton } from "@/components/ui/primitives";
import { api, exportSupervisaoUrl, operadorUrl, type SupervisaoFiltros } from "@/lib/api";
import { cn, fmtDateTime, fmtDay, fmtInt, isoDate } from "@/lib/utils";

const PERIODOS = [
  { v: "", label: "Todo o período" },
  { v: "7", label: "Últimos 7 dias" },
  { v: "30", label: "Últimos 30 dias" },
  { v: "90", label: "Últimos 90 dias" },
];
const fmtNota = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString("pt-BR", { maximumFractionDigits: 1 }));

export default function SupervisaoPage() {
  const [periodo, setPeriodo] = useState("30");
  const [grupo, setGrupo] = useState("");
  const [operador, setOperador] = useState("");
  const [aba, setAba] = useState<"pendente" | "todas" | "falha">("pendente");
  const [page, setPage] = useState(1);

  const filtros: SupervisaoFiltros = useMemo(() => {
    const f: SupervisaoFiltros = {};
    if (periodo) {
      const d = new Date();
      d.setDate(d.getDate() - Number(periodo) + 1);
      f.data_inicio = isoDate(d);
    }
    if (grupo) f.grupo = grupo;
    if (operador) f.operador = operador;
    return f;
  }, [periodo, grupo, operador]);

  const { data: r, isLoading } = useQuery({ queryKey: ["sup-resumo", filtros], queryFn: () => api.supervisaoResumo(filtros) });
  const { data: lista } = useQuery({
    queryKey: ["sup-lista", filtros, aba, page],
    queryFn: () =>
      api.supervisaoAvaliacoes({
        ...filtros,
        page,
        ciencia: aba === "pendente" ? "pendente" : undefined,
        falha_critica: aba === "falha" ? "true" : undefined,
      }),
  });
  const { data: opts } = useQuery({ queryKey: ["options"], queryFn: api.options, staleTime: 300_000 });
  const semEquipe = r?.escopo.restrito && !r.escopo.grupos?.length;
  const paginas = lista ? Math.max(1, Math.ceil(lista.total / lista.page_size)) : 1;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs text-ink-muted">
            {r?.escopo.restrito ? `Sua equipe: ${r.escopo.grupos?.join(", ") || "nenhuma vinculada"}` : "Todas as equipes"}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Supervisão</h1>
        </div>
        <a href={exportSupervisaoUrl(filtros)} className="inline-flex">
          <Button variant="outline" size="sm">
            <Download className="h-3.5 w-3.5" /> Exportar CSV
          </Button>
        </a>
      </header>

      <div className="flex flex-wrap gap-2">
        <Select aria-label="Período" value={periodo} onChange={(e) => (setPeriodo(e.target.value), setPage(1))} className="w-44">
          {PERIODOS.map((p) => (
            <option key={p.v} value={p.v}>
              {p.label}
            </option>
          ))}
        </Select>
        {(opts?.grupos?.length ?? 0) > 1 && (
          <Select aria-label="Equipe" value={grupo} onChange={(e) => (setGrupo(e.target.value), setPage(1))} className="w-52">
            <option value="">Todas as equipes</option>
            {opts!.grupos!.map((g) => (
              <option key={g.nome} value={g.nome}>
                {g.nome}
              </option>
            ))}
          </Select>
        )}
        <Select aria-label="Operador" value={operador} onChange={(e) => (setOperador(e.target.value), setPage(1))} className="w-52">
          <option value="">Todos os operadores</option>
          {opts?.operadores.map((o) => (
            <option key={o.nome} value={o.nome}>
              {o.nome}
            </option>
          ))}
        </Select>
      </div>

      {semEquipe ? (
        <Card>
          <Empty icon={<Users className="h-5 w-5" />} title="Nenhuma equipe vinculada a você">
            Peça a um administrador para vincular sua equipe em Usuários.
          </Empty>
        </Card>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Kpi icon={<ClipboardList className="h-4 w-4" />} label="Avaliações" valor={r ? fmtInt(r.avaliacoes) : undefined} />
            <Kpi
              icon={<Gauge className="h-4 w-4" />}
              label="Nota média"
              valor={r ? fmtNota(r.nota_media) : undefined}
              cls={notaTone(r?.nota_media)}
            />
            <Kpi
              icon={<AlertOctagon className="h-4 w-4" />}
              label="Com falha crítica"
              valor={r ? `${r.falha_critica_pct.toLocaleString("pt-BR")}%` : undefined}
              sub={r ? `${fmtInt(r.falhas_criticas)} avaliações` : undefined}
              cls={r && r.falhas_criticas ? "text-critical" : undefined}
            />
            <Kpi
              icon={<Eye className="h-4 w-4" />}
              label="Aguardando sua ciência"
              valor={r ? fmtInt(r.sem_ciencia) : undefined}
              cls={r && r.sem_ciencia ? "text-warn" : undefined}
            />
          </section>

          <div className="grid gap-4 lg:grid-cols-5">
            <Card title="Nota média por semana" subtitle="Semana da ligação · passe o mouse para ver cada semana" className="lg:col-span-3">
              {isLoading ? <Skeleton className="h-56" /> : <Evolucao dados={r?.evolucao ?? []} />}
            </Card>
            <Card title="Trechos do script mais errados" subtitle="% das avaliações em que o trecho foi errado; divergência ao lado" className="lg:col-span-2">
              {isLoading ? (
                <Skeleton className="h-56" />
              ) : !r?.itens.length ? (
                <Empty icon={<CheckCircle2 className="h-5 w-5 text-good" />} title="Nenhum erro no período" />
              ) : (
                <ol className="space-y-3">
                  {r.itens.slice(0, 7).map((it) => (
                    <li key={it.texto} className="text-xs" title={it.texto}>
                      <div className="mb-1 flex items-baseline justify-between gap-2">
                        <span className="line-clamp-2 text-ink-2">
                          {it.critico && <AlertOctagon className="mr-1 inline h-3 w-3 text-critical" aria-label="crítico" />}
                          {it.texto}
                        </span>
                        <span className="num shrink-0 font-medium text-ink">{it.erro_pct.toLocaleString("pt-BR")}%</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-raised">
                        <div className="h-full rounded-full bg-[var(--series-1)]" style={{ width: `${Math.max(2, it.erro_pct)}%` }} />
                      </div>
                      <div className="mt-0.5 text-[11px] text-ink-muted">
                        {it.secao} · errou {it.errou} de {it.avaliados}
                        {it.divergencia > 0 && ` · divergência ${it.divergencia_pct.toLocaleString("pt-BR")}%`}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          </div>

          <Card title="Operadores" subtitle="Menor nota primeiro">
            {!r?.operadores.length ? (
              <Empty title="Nenhuma avaliação no período" />
            ) : (
              <div className="-mx-4 overflow-x-auto sm:mx-0">
                <table className="w-full min-w-[560px] text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-[11px] uppercase tracking-wide text-ink-muted">
                      <th className="px-4 py-2 font-medium sm:px-0">Operador</th>
                      <th className="py-2 text-right font-medium">Avaliações</th>
                      <th className="py-2 text-right font-medium">Nota média</th>
                      <th className="py-2 text-right font-medium">Falhas críticas</th>
                      <th className="py-2 text-right font-medium">Sem ciência</th>
                      <th className="py-2 pr-4 text-right font-medium sm:pr-0">Última</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {r.operadores.map((o) => (
                      <tr key={o.operador} className="hover:bg-raised/40">
                        <td className="px-4 py-2.5 sm:px-0">
                          <Link href={operadorUrl(o.operador)} className="font-medium hover:underline">
                            {o.operador}
                          </Link>
                          {o.grupo && <div className="text-[11px] text-ink-muted">{o.grupo}</div>}
                        </td>
                        <td className="num py-2.5 text-right">{fmtInt(o.avaliacoes)}</td>
                        <td className={cn("num py-2.5 text-right font-semibold", notaTone(o.nota_media))}>{fmtNota(o.nota_media)}</td>
                        <td className="num py-2.5 text-right">
                          {o.falhas_criticas ? (
                            <Pill tone="critical">
                              <AlertOctagon className="h-3 w-3" /> {o.falhas_criticas}
                            </Pill>
                          ) : (
                            "0"
                          )}
                        </td>
                        <td className="num py-2.5 text-right">{o.sem_ciencia ? <Pill tone="warn">{o.sem_ciencia}</Pill> : "0"}</td>
                        <td className="num py-2.5 pr-4 text-right text-xs text-ink-muted sm:pr-0">{fmtDateTime(o.ultima)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card
            title="Avaliações e feedback"
            subtitle="Abra para ouvir os trechos marcados, ler o feedback e registrar a devolutiva ao operador"
            action={
              <div className="flex rounded-xl bg-raised p-1 text-xs" role="tablist">
                {(
                  [
                    ["pendente", "Sem ciência"],
                    ["falha", "Falha crítica"],
                    ["todas", "Todas"],
                  ] as const
                ).map(([k, l]) => (
                  <button
                    key={k}
                    role="tab"
                    aria-selected={aba === k}
                    onClick={() => (setAba(k), setPage(1))}
                    className={cn("rounded-lg px-3 py-1.5 font-medium text-ink-muted", aba === k && "bg-surface text-ink shadow-sm")}
                  >
                    {l}
                  </button>
                ))}
              </div>
            }
          >
            {!lista ? (
              <Skeleton className="h-40" />
            ) : !lista.itens.length ? (
              <Empty icon={<CheckCircle2 className="h-5 w-5 text-good" />} title={aba === "pendente" ? "Tudo visto" : "Nada aqui"}>
                {aba === "pendente" ? "Nenhuma avaliação aguardando sua ciência." : "Nenhuma avaliação neste filtro."}
              </Empty>
            ) : (
              <ul className="divide-y divide-line">
                {lista.itens.map((a) => (
                  <li key={a.id}>
                    <Link href={`/monitoria/avaliar/${a.call_id}`} className="flex items-start gap-3 py-3 hover:bg-raised/40">
                      <span className={cn("num w-12 shrink-0 text-right text-xl font-semibold", notaTone(a.nota))}>{fmtNota(a.nota)}</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="font-medium">{a.operador_nome}</span>
                          <span className="num text-xs text-ink-muted">{fmtDateTime(a.data_ligacao)}</span>
                          {a.falha_critica && (
                            <Pill tone="critical">
                              <AlertOctagon className="h-3 w-3" /> falha crítica
                            </Pill>
                          )}
                          {a.ciencia ? (
                            <Pill tone="good">
                              <CheckCircle2 className="h-3 w-3" /> ciência de {a.ciencia.por}
                            </Pill>
                          ) : (
                            <Pill tone="warn">sem ciência</Pill>
                          )}
                        </div>
                        {(a.feedback_melhorar || a.observacao) && (
                          <p className="mt-0.5 line-clamp-2 text-xs text-ink-2">
                            {a.feedback_melhorar ? <b className="font-medium">A melhorar: </b> : null}
                            {a.feedback_melhorar || a.observacao}
                          </p>
                        )}
                        <p className="mt-0.5 text-[11px] text-ink-muted">Avaliada por {a.monitora_nome}</p>
                      </div>
                      <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-ink-muted" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {lista && paginas > 1 && (
              <div className="mt-3 flex items-center justify-end gap-2 text-xs text-ink-muted">
                <Button size="sm" variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  Anterior
                </Button>
                <span className="num">
                  {page} / {paginas}
                </span>
                <Button size="sm" variant="ghost" disabled={page >= paginas} onClick={() => setPage((p) => p + 1)}>
                  Próxima
                </Button>
              </div>
            )}
          </Card>
        </>
      )}
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
  const d = payload[0].payload as { semana: string; nota_media: number | null; avaliacoes: number; falhas_criticas: number };
  return (
    <div className="min-w-[180px] rounded-xl border border-line bg-surface p-3 text-xs shadow-pop">
      <div className="mb-1 font-semibold text-ink">Semana de {fmtDay(d.semana)}</div>
      <div className="flex justify-between gap-4 text-ink-2">
        Nota média <b className="num font-medium text-ink">{fmtNota(d.nota_media)}</b>
      </div>
      <div className="flex justify-between gap-4 text-ink-2">
        Avaliações <span className="num text-ink">{fmtInt(d.avaliacoes)}</span>
      </div>
      <div className="flex justify-between gap-4 text-ink-2">
        Falhas críticas <span className="num text-ink">{fmtInt(d.falhas_criticas)}</span>
      </div>
    </div>
  );
}

function Evolucao({ dados }: { dados: { semana: string; nota_media: number | null; avaliacoes: number; falhas_criticas: number }[] }) {
  if (!dados.length) return <Empty title="Sem avaliações no período" />;
  return (
    <div className="h-56" role="img" aria-label={`Nota média por semana: ${dados.map((d) => `${fmtDay(d.semana)} ${fmtNota(d.nota_media)}`).join("; ")}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={dados} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis
            dataKey="semana"
            tickFormatter={(v) => fmtDay(String(v))}
            tick={{ fill: "var(--chart-text)", fontSize: 11 }}
            axisLine={{ stroke: "var(--chart-axis)" }}
            tickLine={false}
          />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fill: "var(--chart-text)", fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip content={<Tip />} cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1 }} />
          <Line
            type="monotone"
            dataKey="nota_media"
            stroke="var(--series-1)"
            strokeWidth={2}
            dot={{ r: 4, fill: "var(--series-1)", stroke: "var(--chart-surface)", strokeWidth: 2 }}
            activeDot={{ r: 6, fill: "var(--series-1)", stroke: "var(--chart-surface)", strokeWidth: 2 }}
            connectNulls
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
