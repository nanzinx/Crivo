"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertTriangle, ArrowRight, ClipboardCheck, FlaskConical, Gauge, Info, Target, UserCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { CallDrawer } from "@/components/calls/call-drawer";
import { Button, Card, Empty, Skeleton } from "@/components/ui/primitives";
import { StatTile } from "@/components/ui/stat-tile";
import { api, type Qualidade } from "@/lib/api";
import { catColor, catLabel, cn, fmtDateTime, fmtInt, fmtPct, fmtUsd } from "@/lib/utils";

const seq = (t: number) => `color-mix(in oklab, var(--seq) ${Math.round(8 + t * 84)}%, var(--chart-surface))`;
const MOTOR: Record<string, string> = { openai: "IA (OpenAI)", local: "Análise local (sem IA)", heuristica: "Heurística (sem chave)" };

export default function QualidadePage() {
  const qc = useQueryClient();
  const { data: q, isLoading } = useQuery({ queryKey: ["qualidade"], queryFn: api.qualidade, refetchInterval: 30_000 });
  const [aberta, setAberta] = useState<number | null>(null);
  const medir = useMutation({
    mutationFn: (n: number) => api.medirQualidade(n),
    onSuccess: (r) => {
      toast.success(`${r.enfileiradas} ligações enviadas para a IA`, {
        description: `Custo estimado: ${fmtUsd(r.custo_estimado_usd)}. Os números se atualizam conforme a fila anda.`,
      });
      qc.invalidateQueries();
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const semIa = q?.gabarito.revisadas_sem_resposta_ia ?? 0;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-2xl">
          <p className="mb-1 flex items-center gap-2 text-xs font-medium text-ink-muted">
            <Gauge className="h-3.5 w-3.5 text-brand" /> A IA comparada com a revisão humana
          </p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Qualidade da IA</h1>
          <p className="mt-2 text-sm text-ink-2">
            Cada revisão feita no detalhe da ligação vira gabarito. Uma amostra aleatória de {q ? `${q.fila.amostra_pct}%` : "algumas"} das
            ligações entra na fila mesmo sem dúvida, para a medição não ficar só nos casos difíceis.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {semIa > 0 && (
            <Button
              variant="outline"
              size="sm"
              loading={medir.isPending}
              onClick={() => {
                const n = Math.min(semIa, 50);
                if (window.confirm(`Rodar a IA em ${n} ligações da escuta manual para comparar? Isso usa a IA e tem custo.`)) medir.mutate(n);
              }}
            >
              <FlaskConical className="h-4 w-4" /> Medir com a escuta manual ({fmtInt(semIa)})
            </Button>
          )}
          <Link href="/ligacoes?revisao=true">
            <Button variant="primary" size="sm">
              <ClipboardCheck className="h-4 w-4" /> Fila de revisão ({fmtInt(q?.fila.pendentes ?? 0)})
            </Button>
          </Link>
        </div>
      </header>

      {isLoading || !q ? (
        <div className="grid gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
          <Skeleton className="h-72 lg:col-span-4" />
        </div>
      ) : q.avaliadas === 0 ? (
        <Card>
          <Empty icon={<Target className="h-5 w-5" />} title="Ainda não há revisões para comparar">
            Abra uma ligação da <Link href="/ligacoes?revisao=true" className="text-brand-ink underline">fila de revisão</Link>, ouça e
            diga se a IA acertou. {semIa > 0 && "Ou use o botão “Medir com a escuta manual”."}
          </Empty>
        </Card>
      ) : (
        <>
          {q.amostra_pequena && (
            <div className="card flex items-start gap-3 border-warn/50 bg-warn/[.06] p-4 text-sm">
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
              <p>
                Ainda são <b className="font-semibold">{fmtInt(q.avaliadas)} revisões</b>. Os percentuais ficam confiáveis a partir de umas 50 e,
                para uma margem de ±5%, perto de 400.
              </p>
            </div>
          )}

          <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile
              hero
              label="Acerto da IA"
              value={q.acuracia}
              format={(n) => fmtPct(n)}
              icon={<Target className="h-4 w-4" />}
              tone={q.acuracia >= 90 ? "good" : q.acuracia >= 75 ? "warn" : "critical"}
              hint={`${fmtInt(q.acertos)} de ${fmtInt(q.avaliadas)} revisões`}
            />
            <StatTile
              label="Divergências confirmadas"
              value={q.divergencias.precisao}
              format={(n) => fmtPct(n)}
              icon={<UserCheck className="h-4 w-4" />}
              tone={q.divergencias.precisao >= 90 ? "good" : q.divergencias.precisao >= 75 ? "warn" : "critical"}
              hint={`${fmtInt(q.divergencias.confirmadas)} de ${fmtInt(q.divergencias.apontadas)} apontadas pela IA`}
              delay={0.04}
            />
            <StatTile
              label="Divergências que a IA deixou passar"
              value={q.divergencias.perdidas}
              format={fmtInt}
              icon={<AlertTriangle className="h-4 w-4" />}
              hint="erros do operador vistos só na revisão"
              delay={0.08}
            />
            <StatTile
              label="Revisões nos últimos 7 dias"
              value={q.fila.revisadas_7d}
              format={fmtInt}
              icon={<ClipboardCheck className="h-4 w-4" />}
              hint={`${fmtInt(q.fila.pendentes)} esperando na fila`}
              delay={0.12}
            />
          </section>

          <div className="grid gap-4 xl:grid-cols-5">
            <Card title="Onde a IA confunde" subtitle="Linhas: o que a revisão disse · colunas: o que a IA disse" className="xl:col-span-3">
              <Confusao q={q} />
            </Card>
            <Card title="A confiança da IA é confiável?" subtitle="Acerto por faixa de confiança" className="xl:col-span-2" delay={0.05}>
              <Calibracao q={q} />
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-5">
            <Card title="Acerto por categoria" subtitle="Precisão: quando a IA diz X, quantas vezes é X · Cobertura: dos X reais, quantos a IA achou" className="xl:col-span-3">
              <PorCategoria q={q} />
            </Card>
            <Card title="Por quem analisou" subtitle="Inclui as ligações resolvidas sem IA (sem fala no áudio)" className="xl:col-span-2" delay={0.05}>
              <ul className="space-y-3">
                {q.por_motor.map((m) => (
                  <li key={m.motor}>
                    <div className="mb-1 flex items-baseline justify-between text-sm">
                      <span>{MOTOR[m.motor] ?? m.motor}</span>
                      <span className="num text-xs text-ink-muted">
                        {fmtPct(m.acuracia)} · {fmtInt(m.n)} revisões
                      </span>
                    </div>
                    <Barra pct={m.acuracia} />
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <Card title="Últimas discordâncias" subtitle="Onde a revisão humana corrigiu a IA: ouça para entender o padrão do erro">
            {q.discordancias.length === 0 ? (
              <Empty title="A revisão concordou com a IA em todos os casos" />
            ) : (
              <ul className="divide-y divide-line">
                {q.discordancias.map((d) => (
                  <li key={d.id}>
                    <button onClick={() => setAberta(d.id)} className="grid w-full gap-1 py-3 text-left hover:bg-raised/40 sm:grid-cols-[110px_1fr_auto] sm:items-center sm:gap-4">
                      <span className="num text-xs text-ink-muted">{fmtDateTime(d.data_ligacao)}</span>
                      <span className="min-w-0">
                        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                          <span className="inline-flex items-center gap-1.5 text-ink-2 line-through decoration-critical/60">
                            <span className="h-2 w-2 rounded-full" style={{ background: catColor(d.ia) }} />
                            {catLabel(d.ia)}
                          </span>
                          <ArrowRight className="h-3 w-3 text-ink-muted" />
                          <span className="inline-flex items-center gap-1.5 font-medium">
                            <span className="h-2 w-2 rounded-full" style={{ background: catColor(d.humano) }} />
                            {catLabel(d.humano)}
                            {d.humano_sub_label && <span className="font-normal text-ink-muted">· {d.humano_sub_label}</span>}
                          </span>
                        </span>
                        {d.observacao && <span className="mt-0.5 block truncate text-xs italic text-ink-muted">“{d.observacao}”</span>}
                      </span>
                      <span className="num text-xs text-ink-muted">
                        confiança {d.confianca != null ? fmtPct(d.confianca * 100, 0) : "–"} · {d.revisado_por}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
      <CallDrawer id={aberta} onClose={() => setAberta(null)} />
    </div>
  );
}

function Barra({ pct, tone }: { pct: number; tone?: string }) {
  return (
    <div className="h-2 overflow-hidden rounded-full bg-raised">
      <motion.div
        className={cn("h-full rounded-full", tone ?? (pct >= 90 ? "bg-good" : pct >= 75 ? "bg-warn" : "bg-critical"))}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.6 }}
      />
    </div>
  );
}

function Confusao({ q }: { q: Qualidade }) {
  const cats = q.confusao.categorias;
  return (
    <div className="flex flex-col gap-3">
      <div className="scroll-thin overflow-x-auto">
        <table className="w-full min-w-[560px] border-separate border-spacing-[2px] text-xs">
          <thead>
            <tr className="text-ink-2">
              <th className="sticky left-0 z-10 bg-surface pb-2 pr-3 text-left align-bottom font-medium">Revisão ↓ · IA →</th>
              {cats.map((c) => (
                <th key={c} className="pb-2 text-center align-bottom font-medium" title={catLabel(c)}>
                  <span className="mx-auto mb-1 block h-2 w-2 rounded-full" style={{ background: catColor(c) }} />
                  <span className="whitespace-nowrap">{catLabel(c).replace("Não é o cliente", "Não é cliente")}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {q.confusao.linhas.map((l) => (
              <tr key={l.humano}>
                <td className="sticky left-0 z-10 whitespace-nowrap bg-surface pr-3 text-ink">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full" style={{ background: catColor(l.humano) }} />
                    {catLabel(l.humano)}
                  </span>
                </td>
                {cats.map((c) => {
                  const v = l.ia[c] || 0;
                  const share = l.total ? v / l.total : 0;
                  const certo = c === l.humano;
                  return (
                    <td
                      key={c}
                      className={cn("num h-9 rounded-[4px] text-center", v && !certo && "ring-2 ring-inset ring-critical/70")}
                      style={{ background: v ? seq(share) : "transparent", color: share > 0.55 ? "#fff" : "rgb(var(--ink))" }}
                      title={`Revisão: ${catLabel(l.humano)} · IA: ${catLabel(c)} = ${v} (${fmtPct(share * 100)})`}
                    >
                      {v ? fmtInt(v) : <span className="text-ink-muted/50">·</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-ink-muted">A diagonal são os acertos. Contorno vermelho = a IA errou; quanto mais escuro, mais frequente o erro.</p>
    </div>
  );
}

function Calibracao({ q }: { q: Qualidade }) {
  const minimo = Math.round(q.fila.confianca_minima * 100);
  return (
    <div className="flex flex-col gap-4">
      <ul className="space-y-3">
        {q.por_confianca.map((f) => (
          <li key={f.faixa}>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span>Confiança {f.faixa}</span>
              <span className="num text-xs text-ink-muted">{f.n ? `${fmtPct(f.acuracia)} de acerto · ${fmtInt(f.n)} revisões` : "sem revisões"}</span>
            </div>
            <Barra pct={f.n ? f.acuracia : 0} />
          </li>
        ))}
      </ul>
      <p className="rounded-xl bg-raised p-3 text-xs text-ink-2">
        Hoje, divergências com confiança abaixo de <b className="font-semibold">{minimo}%</b> não acusam o operador: vão para a fila de revisão. Se a
        faixa logo acima desse limite também errar muito, vale subir <code className="font-mono">CONFIANCA_MINIMA_DIVERGENCIA</code>; se a faixa
        de baixo acertar quase sempre, dá para baixar e revisar menos.
      </p>
    </div>
  );
}

function PorCategoria({ q }: { q: Qualidade }) {
  return (
    <div className="scroll-thin overflow-x-auto">
      <table className="w-full min-w-[480px] text-sm">
        <thead className="text-left text-[11px] uppercase tracking-wide text-ink-muted">
          <tr>
            <th className="pb-2 font-medium">Categoria</th>
            <th className="pb-2 text-right font-medium">Revisões</th>
            <th className="w-[28%] pb-2 pl-4 font-medium">Precisão</th>
            <th className="w-[28%] pb-2 pl-4 font-medium">Cobertura</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {q.por_categoria.map((c) => (
            <tr key={c.codigo}>
              <td className="py-2.5">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: catColor(c.codigo) }} />
                  {catLabel(c.codigo)}
                </span>
              </td>
              <td className="num py-2.5 text-right text-ink-2">{fmtInt(c.humano)}</td>
              <td className="py-2.5 pl-4">
                <div className="num mb-1 text-xs text-ink-2">{c.ia ? fmtPct(c.precisao) : "–"}</div>
                <Barra pct={c.ia ? c.precisao : 0} />
              </td>
              <td className="py-2.5 pl-4">
                <div className="num mb-1 text-xs text-ink-2">{c.humano ? fmtPct(c.recall) : "–"}</div>
                <Barra pct={c.humano ? c.recall : 0} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
