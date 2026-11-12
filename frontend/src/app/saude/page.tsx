"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertOctagon,
  AlertTriangle,
  Bot,
  CheckCircle2,
  CloudDownload,
  FileSpreadsheet,
  FolderInput,
  Inbox,
  Loader2,
  PlayCircle,
  PlugZap,
  RefreshCw,
  Upload,
  XCircle,
} from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { CallDrawer } from "@/components/calls/call-drawer";
import { Button, Card, Empty, Pill, Skeleton } from "@/components/ui/primitives";
import { AnimatedNumber } from "@/components/ui/stat-tile";
import { api, type Custos, type Evento, type Saude } from "@/lib/api";
import { STATUS_LABEL, cn, fmtAgo, fmtDateTime, fmtDay, fmtInt, fmtUsd, isoDate } from "@/lib/utils";

export default function SaudePage() {
  const qc = useQueryClient();
  const { data, isLoading, isFetching, refetch } = useQuery({ queryKey: ["saude"], queryFn: api.saude, refetchInterval: 15_000 });
  const [open, setOpen] = useState<number | null>(null);
  const refresh = () => qc.invalidateQueries();

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-1 text-xs font-medium text-ink-muted">
            {data ? `Atualizado ${fmtAgo(data.gerado_em)} · a cada 15s` : "Carregando…"}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Saúde do sistema</h1>
        </div>
        <Button variant="ghost" size="sm" onClick={() => refetch()}>
          <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} /> Atualizar
        </Button>
      </header>

      {isLoading || !data ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-40 lg:col-span-3" />
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <>
          <Alertas alertas={data.alertas} />

          <section className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Contador label="Na fila agora" value={data.fila.tamanho} icon={<Loader2 className={cn("h-4 w-4", data.fila.tamanho > 0 && "animate-spin")} />} />
            <Contador label="Recebidas em 24h" value={data.recebidas_24h} icon={<Inbox className="h-4 w-4" />} />
            <Contador label={STATUS_LABEL.pending} value={data.status_ligacoes.pending + data.status_ligacoes.awaiting_ai} icon={<PlayCircle className="h-4 w-4" />} />
            <Contador label="Com erro" value={data.status_ligacoes.error} icon={<XCircle className="h-4 w-4" />} tone={data.status_ligacoes.error ? "critical" : undefined} />
            <Contador label="Qualificadas" value={data.status_ligacoes.done} icon={<CheckCircle2 className="h-4 w-4" />} tone="good" />
          </section>

          <div className="grid gap-4 lg:grid-cols-5">
            <Card title="Integrações" subtitle="Último resultado de cada etapa do fluxo" className="lg:col-span-3">
              <Integracoes data={data} />
            </Card>
            <Card title="Ações" subtitle="Alimentar e processar a base" className="lg:col-span-2">
              <Acoes onDone={refresh} pendentes={data.status_ligacoes.pending + data.status_ligacoes.error + data.status_ligacoes.awaiting_ai} />
            </Card>
          </div>

          <CustoIA c={data.custos} />

          <Card title="Erros recentes" subtitle="Ligações que falharam — reprocesse após corrigir a causa">
            {data.erros_recentes.length === 0 ? (
              <Empty icon={<CheckCircle2 className="h-5 w-5 text-good" />} title="Nenhuma ligação com erro" />
            ) : (
              <ul className="divide-y divide-line">
                {data.erros_recentes.map((e) => (
                  <li key={e.id}>
                    <button onClick={() => setOpen(e.id)} className="grid w-full grid-cols-[auto_1fr] gap-3 py-3 text-left hover:bg-raised/40 sm:grid-cols-[120px_160px_1fr]">
                      <span className="num text-xs text-ink-muted">{fmtDateTime(e.data_ligacao)}</span>
                      <span className="truncate text-xs text-ink-2 sm:block">{e.operador_nome ?? `#${e.id_ligacao ?? e.id}`}</span>
                      <span className="col-span-2 truncate font-mono text-xs text-critical sm:col-span-1">{e.erro}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
      <CallDrawer id={open} onClose={() => setOpen(null)} />
    </div>
  );
}

function CustoIA({ c }: { c: Custos }) {
  const [hover, setHover] = useState<number | null>(null);
  // Escala pelos gastos reais; a linha do teto só aparece quando cabe no gráfico (a barra ao lado já mostra o teto)
  const pico = Math.max(...c.serie.map((d) => d.usd), 0.0001);
  const tetoNoGrafico = c.teto_diario_usd > 0 && c.teto_diario_usd <= pico * 1.6;
  const max = tetoNoGrafico ? Math.max(pico, c.teto_diario_usd) * 1.08 : pico * 1.08;
  const totalMes = c.ligacoes_com_ia_mes + c.resolvidas_sem_ia_mes;
  const pctSemIa = totalMes ? (100 * c.resolvidas_sem_ia_mes) / totalMes : 0;
  const sel = hover != null ? c.serie[hover] : null;
  const tetoTone = c.teto_pct == null ? "" : c.teto_pct >= 100 ? "bg-critical" : c.teto_pct >= 80 ? "bg-warn" : "bg-good";

  return (
    <Card
      title="Custo de IA"
      subtitle={`Estimado pelo preço de tabela · ${c.modelo_transcricao} + ${c.modelo_classificacao}${c.diarizacao ? " · com separação por falante" : ""}`}
    >
      <div className="grid gap-5 lg:grid-cols-5">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-4 lg:col-span-2">
          <Num label="Hoje" valor={fmtUsd(c.hoje_usd)} />
          <Num label="Neste mês" valor={fmtUsd(c.mes_usd)} />
          <Num label="Média por ligação com IA" valor={fmtUsd(c.custo_medio_usd)} sub={`${fmtInt(c.minutos_transcritos_mes)} min transcritos no mês`} />
          <Num
            label="Resolvidas sem IA no mês"
            valor={fmtInt(c.resolvidas_sem_ia_mes)}
            sub={totalMes ? `${pctSemIa.toFixed(0)}% das analisadas (sem fala no áudio)` : "mudas detectadas localmente"}
          />
          <div className="col-span-2">
            {c.teto_diario_usd > 0 ? (
              <>
                <div className="mb-1 flex justify-between text-xs text-ink-2">
                  <span>Teto diário</span>
                  <span className="num">
                    {fmtUsd(c.hoje_usd)} de {fmtUsd(c.teto_diario_usd)} ({(c.teto_pct ?? 0).toFixed(0)}%)
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-raised">
                  <motion.div className={cn("h-full rounded-full", tetoTone)} initial={{ width: 0 }} animate={{ width: `${Math.min(100, c.teto_pct ?? 0)}%` }} />
                </div>
              </>
            ) : (
              <p className="text-xs text-ink-muted">
                Sem teto diário. Defina <code className="font-mono">IA_TETO_DIARIO_USD</code> no .env para limitar o gasto.
              </p>
            )}
          </div>
        </dl>

        <div className="lg:col-span-3">
          <div className="mb-2 flex items-baseline justify-between text-xs">
            <span className="font-medium text-ink-2">Gasto por dia (14 dias)</span>
            <span className="num text-ink-muted">{sel ? `${fmtDay(sel.data)}: ${fmtUsd(sel.usd)}` : "toque ou passe o mouse numa barra"}</span>
          </div>
          <div className="relative mt-4 flex h-32 items-end gap-[2px] border-b border-line" role="img" aria-label="Gasto diário com IA nos últimos 14 dias">
            {tetoNoGrafico && (
              <div className="pointer-events-none absolute inset-x-0 border-t border-dashed border-critical/60" style={{ bottom: `${(c.teto_diario_usd / max) * 100}%` }}>
                <span className="absolute -top-3.5 left-0 bg-surface pr-1 text-[10px] text-critical">teto diário</span>
              </div>
            )}
            {c.serie.map((d, i) => (
              <div
                key={d.data}
                className="group flex h-full flex-1 items-end justify-center"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                title={`${fmtDay(d.data)}: ${fmtUsd(d.usd)}`}
              >
                <motion.div
                  className={cn("w-full max-w-[24px] rounded-t-[4px] transition-opacity", hover != null && hover !== i && "opacity-40")}
                  style={{ background: "var(--seq)" }}
                  initial={{ height: 0 }}
                  animate={{ height: `${Math.max(d.usd > 0 ? 2 : 0, (d.usd / max) * 100)}%` }}
                  transition={{ duration: 0.5, delay: i * 0.02 }}
                />
              </div>
            ))}
          </div>
          <div className="num mt-1 flex justify-between text-[10px] text-ink-muted">
            <span>{fmtDay(c.serie[0].data)}</span>
            <span>{fmtDay(c.serie[c.serie.length - 1].data)}</span>
          </div>
        </div>
      </div>
    </Card>
  );
}

function Num({ label, valor, sub }: { label: string; valor: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-xs text-ink-muted">{label}</dt>
      <dd className="num text-xl font-semibold tracking-tight">{valor}</dd>
      {sub && <dd className="truncate text-[11px] text-ink-muted">{sub}</dd>}
    </div>
  );
}

function Alertas({ alertas }: { alertas: Saude["alertas"] }) {
  if (!alertas.length) {
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card flex items-center gap-3 border-good/30 bg-good/[.05] p-4">
        <span className="grid h-10 w-10 place-items-center rounded-2xl bg-good/15 text-good">
          <CheckCircle2 className="h-5 w-5" />
        </span>
        <div>
          <p className="text-sm font-semibold">Tudo funcionando</p>
          <p className="text-xs text-ink-muted">Nenhum alerta no momento.</p>
        </div>
      </motion.div>
    );
  }
  return (
    <ul className="grid gap-2 md:grid-cols-2">
      <AnimatePresence>
        {alertas.map((a, i) => {
          const crit = a.nivel === "critico";
          const Icon = crit ? AlertOctagon : AlertTriangle;
          return (
            <motion.li
              key={a.titulo + a.mensagem}
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.05 }}
              className={cn("card flex items-start gap-3 p-4", crit ? "border-critical/40 bg-critical/[.04]" : "border-warn/50 bg-warn/[.06]")}
            >
              <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-xl", crit ? "bg-critical/15 text-critical" : "bg-warn/20 text-ink")}>
                <Icon className="h-[18px] w-[18px]" />
              </span>
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm font-semibold">
                  {a.titulo} <Pill tone={crit ? "critical" : "warn"}>{crit ? "Crítico" : "Atenção"}</Pill>
                </p>
                <p className="mt-0.5 break-words text-xs text-ink-2">{a.mensagem}</p>
              </div>
            </motion.li>
          );
        })}
      </AnimatePresence>
    </ul>
  );
}

function Contador({ label, value, icon, tone }: { label: string; value: number; icon: ReactNode; tone?: "good" | "critical" }) {
  return (
    <div className="card flex items-center gap-3 p-4">
      <span
        className={cn(
          "grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-raised text-ink-2",
          tone === "good" && "bg-good/10 text-good",
          tone === "critical" && "bg-critical/10 text-critical",
        )}
      >
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-xl font-semibold tracking-tight">
          <AnimatedNumber value={value} format={fmtInt} />
        </div>
        <div className="truncate text-xs text-ink-muted">{label}</div>
      </div>
    </div>
  );
}

const ORDEM = ["argus_webhook", "argus_polling", "argus_sync", "argus_download", "ia", "importacao_local", "cruzamento"];

function Integracoes({ data }: { data: Saude }) {
  const ev = data.eventos;
  const chaves = [...ORDEM.filter((k) => ev[k]), ...Object.keys(ev).filter((k) => !ORDEM.includes(k))];
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-2 sm:grid-cols-2">
        <Config
          icon={<Bot className="h-4 w-4" />}
          title="IA (OpenAI)"
          ok={data.integracoes.ia.configurada}
          detail={data.integracoes.ia.configurada ? `${data.integracoes.ia.modelo} + ${data.integracoes.ia.transcricao}` : "OPENAI_API_KEY ausente"}
        />
        <Config
          icon={<PlugZap className="h-4 w-4" />}
          title="Argus"
          ok={data.integracoes.argus.configurado}
          detail={
            data.integracoes.argus.configurado
              ? data.integracoes.argus.campanhas.length
                ? `Campanhas ${data.integracoes.argus.campanhas.join(", ")} · polling ${data.integracoes.argus.polling_minutos} min`
                : "Sem ARGUS_CAMPAIGN_IDS (polling desligado)"
              : "ARGUS_TOKEN ausente"
          }
        />
      </div>
      {chaves.length === 0 ? (
        <Empty title="Nenhum evento registrado ainda">Os eventos aparecem quando chegam webhooks, rodam importações ou a IA processa ligações.</Empty>
      ) : (
        <ol className="relative space-y-1 before:absolute before:bottom-3 before:left-[15px] before:top-3 before:w-px before:bg-line">
          {chaves.map((k) => (
            <EventoRow key={k} e={ev[k]} />
          ))}
        </ol>
      )}
    </div>
  );
}

function Config({ icon, title, ok, detail }: { icon: ReactNode; title: string; ok: boolean; detail: string }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-line p-3">
      <span className="grid h-8 w-8 place-items-center rounded-xl bg-raised text-ink-2">{icon}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-sm font-medium">
          {title}
          <Pill tone={ok ? "good" : "warn"}>{ok ? "Configurado" : "Pendente"}</Pill>
        </div>
        <div className="truncate text-xs text-ink-muted" title={detail}>
          {detail}
        </div>
      </div>
    </div>
  );
}

function EventoRow({ e }: { e: Evento }) {
  const Icon = e.ok ? CheckCircle2 : XCircle;
  return (
    <li className="relative flex items-start gap-3 rounded-xl py-2 pl-0 pr-2">
      <span className={cn("relative z-10 grid h-8 w-8 shrink-0 place-items-center rounded-full border-4 border-surface", e.ok ? "bg-good/15 text-good" : "bg-critical/15 text-critical")}>
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1 pt-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <span className="text-sm font-medium">{e.nome}</span>
          <span className="text-[11px] text-ink-muted">
            {e.ok ? "OK" : "Falhou"} {fmtAgo(e.em)}
          </span>
        </div>
        {e.detalhe && <p className={cn("mt-0.5 break-words text-xs", e.ok ? "text-ink-muted" : "text-critical")}>{e.detalhe}</p>}
        {!e.ok && e.ultimo_sucesso_em && <p className="mt-0.5 text-[11px] text-ink-muted">Último sucesso {fmtAgo(e.ultimo_sucesso_em)}</p>}
      </div>
    </li>
  );
}

function useAcao<T>(fn: () => Promise<T>, onDone: () => void, ok: (r: T) => string) {
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      toast.success(ok(r));
      onDone();
    },
    onError: (e) => toast.error((e as Error).message),
  });
}

function Acoes({ onDone, pendentes }: { onDone: () => void; pendentes: number }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [ini, setIni] = useState(isoDate(new Date()));
  const [fim, setFim] = useState(isoDate(new Date()));

  const importar = useAcao(api.importarLocal, onDone, (r) => {
    const p = (r as { pasta?: { novas?: number; vinculadas?: number }; cruzamento?: { linhas_enriquecidas?: number } });
    return `Importação concluída: ${p.pasta?.novas ?? 0} novas, ${p.pasta?.vinculadas ?? 0} vinculadas, ${p.cruzamento?.linhas_enriquecidas ?? 0} cruzadas`;
  });
  const processar = useAcao(api.processarPendentes, onDone, (r) => `${r.enfileiradas} ligações enviadas para a IA`);
  const recentes = useAcao(() => api.sincronizarArgus({ ultimos_minutos: 15 }), onDone, (r) => `${r.ligacoes} ligações recebidas do Argus`);
  const backfill = useAcao(() => api.sincronizarArgus({ data_inicio: ini, data_fim: fim }), onDone, (r) => `${r.ligacoes} ligações recebidas do Argus`);
  const cruzar = useMutation({
    mutationFn: (f: File) => api.cruzar(f),
    onSuccess: (r) => {
      toast.success(`${r.linhas_enriquecidas} ligações cruzadas · ${r.divergencias_encontradas} divergências`, {
        description: r.aviso ?? (r.sem_correspondencia ? `${r.sem_correspondencia} linhas sem ligação correspondente` : undefined),
      });
      onDone();
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const onFile = (f?: File | null) => f && cruzar.mutate(f);

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          onFile(e.dataTransfer.files?.[0]);
        }}
        onClick={() => fileRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && fileRef.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-line p-5 text-center transition",
          drag && "border-brand bg-brand-soft/60",
          cruzar.isPending && "pointer-events-none opacity-60",
        )}
      >
        <span className="grid h-10 w-10 place-items-center rounded-2xl bg-brand-soft text-brand-ink">
          {cruzar.isPending ? <Loader2 className="h-5 w-5 animate-spin" /> : <FileSpreadsheet className="h-5 w-5" />}
        </span>
        <p className="text-sm font-medium">Cruzar relatório da discadora</p>
        <p className="text-xs text-ink-muted">
          Arraste o CSV de ligações detalhadas do Argus ou <span className="text-brand-ink underline">clique para escolher</span>
        </p>
        <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={(e) => onFile(e.target.files?.[0])} />
      </div>

      <div className="flex min-w-0 flex-col gap-2">
        <Acao icon={<FolderInput className="h-4 w-4" />} title="Importar acervo local" desc="Pasta de gravações + relatórios configurados no .env" onClick={() => importar.mutate()} loading={importar.isPending} />
        <Acao icon={<Upload className="h-4 w-4" />} title="Processar pendentes" desc={`${fmtInt(pendentes)} ligações pendentes ou com erro`} onClick={() => processar.mutate()} loading={processar.isPending} />
        <Acao icon={<CloudDownload className="h-4 w-4" />} title="Buscar no Argus (15 min)" desc="Puxa as ligações mais recentes agora" onClick={() => recentes.mutate()} loading={recentes.isPending} />
      </div>

      <div className="rounded-2xl border border-line p-3">
        <p className="mb-2 text-xs font-medium text-ink-2">Recuperar período no Argus</p>
        <div className="flex flex-wrap items-center gap-2">
          <input type="date" value={ini} onChange={(e) => setIni(e.target.value)} className="h-9 flex-1 rounded-xl border border-line bg-surface px-2 text-sm" aria-label="Início" />
          <input type="date" value={fim} onChange={(e) => setFim(e.target.value)} className="h-9 flex-1 rounded-xl border border-line bg-surface px-2 text-sm" aria-label="Fim" />
          <Button size="md" variant="primary" onClick={() => backfill.mutate()} loading={backfill.isPending}>
            Buscar
          </Button>
        </div>
      </div>
    </div>
  );
}

function Acao({ icon, title, desc, onClick, loading }: { icon: ReactNode; title: string; desc: string; onClick: () => void; loading?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="flex w-full min-w-0 items-center gap-3 rounded-2xl border border-line p-3 text-left transition hover:border-ink/20 hover:bg-raised/50 active:scale-[.99] disabled:opacity-60"
    >
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-raised text-ink-2">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}</span>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{title}</span>
        <span className="block truncate text-xs text-ink-muted">{desc}</span>
      </span>
    </button>
  );
}
