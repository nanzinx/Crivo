"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Download, Ear, PhoneCall, PhoneOff, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Suspense } from "react";
import { CategoryBreakdown } from "@/components/charts/category-breakdown";
import { ContrastMatrix, HourHeatmap } from "@/components/charts/heat";
import { DESLIG, OperatorRanking, SplitBar } from "@/components/charts/ranking";
import { TimelineChart } from "@/components/charts/timeline-chart";
import { RecentDivergences } from "@/components/calls/recent-divergences";
import { FilterBar } from "@/components/filters/filter-bar";
import { useFilters } from "@/components/filters/use-filters";
import { Button, Card, Empty, Skeleton } from "@/components/ui/primitives";
import { StatTile } from "@/components/ui/stat-tile";
import { api, exportUrl } from "@/lib/api";
import { fmtInt, fmtPct } from "@/lib/utils";

export default function Page() {
  return (
    <Suspense>
      <Dashboard />
    </Suspense>
  );
}

function Dashboard() {
  const { filters: f, setFilters, query } = useFilters();
  const router = useRouter();
  const opts = { placeholderData: keepPreviousData, refetchInterval: 30_000 } as const;
  const summary = useQuery({ queryKey: ["summary", query], queryFn: () => api.summary(f), ...opts });
  const timeline = useQuery({ queryKey: ["timeline", query], queryFn: () => api.timeline(f), ...opts });
  const horas = useQuery({ queryKey: ["horas", query], queryFn: () => api.horas(f), ...opts });

  const s = summary.data;
  const muda = s?.categorias.find((c) => c.codigo === "LIGACAO_MUDA");
  const emNeg = s?.categorias.find((c) => c.codigo === "EM_NEGOCIACAO");
  const pendentes = (s?.status.pending ?? 0) + (s?.status.awaiting_ai ?? 0);
  const loading = summary.isLoading;
  const vazio = s && s.total === 0;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-1 flex items-center gap-2 text-xs font-medium text-ink-muted">
            <Sparkles className="h-3.5 w-3.5 text-brand" /> Tabulação do operador × análise da gravação
          </p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Visão geral</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => [summary, timeline, horas].forEach((q) => q.refetch())}
            aria-label="Atualizar agora"
          >
            <RefreshCw className={summary.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            <span className="hidden sm:inline">Atualiza a cada 30s</span>
          </Button>
          <a href={exportUrl(f)} download>
            <Button variant="primary" size="sm">
              <Download className="h-4 w-4" /> Exportar CSV
            </Button>
          </a>
        </div>
      </header>

      <FilterBar />

      {summary.isError && (
        <div className="card flex items-center gap-3 border-critical/40 p-4 text-sm">
          <AlertTriangle className="h-5 w-5 shrink-0 text-critical" />
          <span>
            Não foi possível falar com a API. Verifique se o backend está rodando em <code className="font-mono text-xs">BACKEND_URL</code>.
            <span className="block text-xs text-ink-muted">{(summary.error as Error).message}</span>
          </span>
        </div>
      )}

      {/* KPIs */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatTile
          hero
          label="Ligações"
          value={s?.total}
          format={fmtInt}
          loading={loading}
          icon={<PhoneCall className="h-4 w-4" />}
          hint={s ? `${fmtInt(pendentes)} aguardando análise` : undefined}
        />
        <StatTile
          label="Qualificadas"
          value={s?.qualificadas}
          format={fmtInt}
          loading={loading}
          icon={<ShieldCheck className="h-4 w-4" />}
          hint={s?.total ? `${fmtPct((100 * s.qualificadas) / s.total)} do total` : undefined}
          delay={0.04}
        />
        <StatTile
          label="Divergência"
          value={s?.divergencias.taxa}
          format={(n) => fmtPct(n)}
          loading={loading}
          tone={s && s.divergencias.taxa >= 20 ? "critical" : s && s.divergencias.taxa >= 10 ? "warn" : "good"}
          icon={<AlertTriangle className="h-4 w-4" />}
          hint={s ? `${fmtInt(s.divergencias.total)} de ${fmtInt(s.divergencias.comparaveis)} comparáveis` : undefined}
          onClick={() => setFilters({ divergencia: f.divergencia === "true" ? "" : "true" })}
          active={f.divergencia === "true"}
          delay={0.08}
        />
        <StatTile
          label="Em negociação"
          value={emNeg?.pct ?? (s ? 0 : undefined)}
          format={(n) => fmtPct(n)}
          loading={loading}
          icon={<Sparkles className="h-4 w-4" />}
          hint={emNeg ? `${fmtInt(emNeg.total)} ligações` : undefined}
          onClick={() => setFilters({ categoria: f.categoria === "EM_NEGOCIACAO" ? "" : "EM_NEGOCIACAO", subcategoria: "" })}
          active={f.categoria === "EM_NEGOCIACAO"}
          delay={0.12}
        />
        <StatTile
          label="Ligações mudas"
          value={muda?.pct ?? (s ? 0 : undefined)}
          format={(n) => fmtPct(n)}
          loading={loading}
          icon={<PhoneOff className="h-4 w-4" />}
          hint={muda ? `${fmtInt(muda.total)} ligações` : undefined}
          onClick={() => setFilters({ categoria: f.categoria === "LIGACAO_MUDA" ? "" : "LIGACAO_MUDA", subcategoria: "" })}
          active={f.categoria === "LIGACAO_MUDA"}
          delay={0.16}
        />
        <StatTile
          label="Revisão humana"
          value={s?.revisao}
          format={fmtInt}
          loading={loading}
          tone={s && s.revisao > 0 ? "warn" : undefined}
          icon={<Ear className="h-4 w-4" />}
          hint="IA sem segurança: alguém precisa ouvir"
          onClick={() => setFilters({ revisao: f.revisao === "true" ? "" : "true" })}
          active={f.revisao === "true"}
          delay={0.2}
        />
      </section>

      {vazio ? (
        <Card>
          <Empty icon={<PhoneCall className="h-5 w-5" />} title="Nenhuma ligação neste filtro">
            Ajuste o período ou importe gravações em <Link href="/saude" className="text-brand-ink underline">Saúde do sistema</Link>.
          </Empty>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-5">
            <Card title="Resultado das ligações" subtitle="Classificação da IA sobre a gravação" className="lg:col-span-2" delay={0.05}>
              {s ? (
                <CategoryBreakdown
                  data={s.categorias}
                  selected={f.categoria}
                  onSelect={(c) => setFilters({ categoria: c ?? "", subcategoria: "" })}
                />
              ) : (
                <Skeleton className="h-64" />
              )}
            </Card>
            <Card title="Volume diário por categoria" subtitle="Ligações qualificadas por dia" className="lg:col-span-3" delay={0.1}>
              {timeline.data ? (
                timeline.data.length ? (
                  <TimelineChart data={timeline.data} />
                ) : (
                  <Empty title="Sem ligações qualificadas no período" />
                )
              ) : (
                <Skeleton className="h-72" />
              )}
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-5">
            <Card
              title="Matriz de contraste"
              subtitle="Como cada tabulação do operador foi classificada pela IA"
              className="xl:col-span-3"
              delay={0.05}
            >
              {s ? (
                s.matriz_contraste.length ? (
                  <ContrastMatrix
                    data={s.matriz_contraste}
                    onPick={(tab) => router.push(`/ligacoes?q=${encodeURIComponent(tab)}&divergencia=true`)}
                  />
                ) : (
                  <Empty title="Sem tabulações do operador">Envie o relatório da discadora em Saúde do sistema para cruzar os dados.</Empty>
                )
              ) : (
                <Skeleton className="h-72" />
              )}
            </Card>
            <Card title="Operadores" subtitle="Taxa de divergência entre tabulação e gravação" className="xl:col-span-2" delay={0.1}>
              {s ? (
                s.ranking_operadores.length ? (
                  <OperatorRanking data={s.ranking_operadores} selected={f.operador} onSelect={(op) => setFilters({ operador: op ?? "" })} />
                ) : (
                  <Empty title="Sem operadores identificados" />
                )
              ) : (
                <Skeleton className="h-72" />
              )}
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-5">
            <Card title="Horário × resultado" subtitle="Quando cada tipo de ligação acontece" className="xl:col-span-3" delay={0.05}>
              {horas.data ? <HourHeatmap data={horas.data} /> : <Skeleton className="h-56" />}
            </Card>
            <Card title="Operação" subtitle="Quem desliga, equipes, discagem e troncos" className="xl:col-span-2" delay={0.1}>
              {s ? (
                <div className="flex flex-col gap-5">
                  <SplitBar title="Quem desligou" data={s.desligamentos} labels={DESLIG} />
                  <SplitBar title="Equipe" data={s.agentes} />
                  <SplitBar title="Tipo de discagem" data={s.discagens} labels={{ ATIVO: "Ativo", URA: "URA" }} />
                  <SplitBar title="Tronco" data={s.troncos} />
                </div>
              ) : (
                <Skeleton className="h-56" />
              )}
            </Card>
          </div>

          <RecentDivergences />
        </>
      )}
    </div>
  );
}
