"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  ChevronDown,
  Copy,
  Headphones,
  Pause,
  Play,
  Quote,
  RefreshCw,
  UserRound,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { usePlayer } from "@/components/player/player-context";
import { Button, CategoryBadge, Meter, Pill, Skeleton } from "@/components/ui/primitives";
import { api, type Call } from "@/lib/api";
import { DESLIG_LABEL, STATUS_LABEL, catLabel, cn, fmtDateTime, fmtDur, fmtPhone } from "@/lib/utils";

export function PlayButton({ call, queue, size = "md" }: { call: Call; queue?: Call[]; size?: "sm" | "md" }) {
  const p = usePlayer();
  const isCur = p.current?.id === call.id;
  const isPlaying = isCur && p.playing;
  return (
    <button
      disabled={!call.tem_audio}
      onClick={(e) => {
        e.stopPropagation();
        p.play(call, queue);
      }}
      aria-label={isPlaying ? "Pausar gravação" : "Ouvir gravação"}
      title={call.tem_audio ? "Ouvir gravação" : "Sem áudio"}
      className={cn(
        "relative grid shrink-0 place-items-center rounded-full border transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-30",
        size === "sm" ? "h-8 w-8" : "h-9 w-9",
        isCur ? "border-brand bg-brand text-white" : "border-line bg-surface text-ink hover:border-ink/30",
      )}
    >
      {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="ml-0.5 h-3.5 w-3.5" />}
      {isPlaying && <span className="absolute inset-0 animate-pulse-ring rounded-full border-2 border-brand" />}
    </button>
  );
}

export function CallDrawer({ id, onClose, queue }: { id: number | null; onClose: () => void; queue?: Call[] }) {
  useEffect(() => {
    if (!id) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [id, onClose]);

  return (
    <AnimatePresence>
      {id && (
        <>
          <motion.div
            className="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            role="dialog"
            aria-modal
            aria-label="Detalhes da ligação"
            className="fixed inset-x-0 bottom-0 top-10 z-50 flex flex-col overflow-hidden rounded-t-3xl border border-line bg-surface shadow-pop sm:inset-y-0 sm:left-auto sm:right-0 sm:top-0 sm:w-[560px] sm:rounded-none sm:rounded-l-3xl"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 40 }}
          >
            <Detail id={id} onClose={onClose} queue={queue} />
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function Detail({ id, onClose, queue }: { id: number; onClose: () => void; queue?: Call[] }) {
  const qc = useQueryClient();
  const { data: c, isLoading } = useQuery({ queryKey: ["call", id], queryFn: () => api.call(id) });
  const [showRaw, setShowRaw] = useState(false);
  const reprocess = useMutation({
    mutationFn: () => api.reprocessar(id),
    onSuccess: (r) => {
      toast.success(r.enfileirada ? "Ligação enviada para nova análise" : "Ligação já está na fila");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["call", id] }), 2500);
    },
    onError: (e) => toast.error(`Falha ao reprocessar: ${(e as Error).message}`),
  });

  return (
    <>
      <header className="relative flex items-start gap-3 border-b border-line p-4 pt-6 sm:p-5">
        <div className="absolute left-1/2 top-2 h-1 w-10 -translate-x-1/2 rounded-full bg-line sm:hidden" aria-hidden />
        <div className="min-w-0 flex-1">
          {isLoading || !c ? (
            <Skeleton className="h-6 w-48" />
          ) : (
            <>
              <div className="flex items-center gap-2">
                <h2 className="truncate text-lg font-semibold tracking-tight">{c.cliente_identificado || c.nome_esperado || "Cliente não identificado"}</h2>
                {c.status !== "done" && <Pill tone={c.status === "error" ? "critical" : "neutral"}>{STATUS_LABEL[c.status] ?? c.status}</Pill>}
              </div>
              <p className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-ink-muted">
                <span>{fmtDateTime(c.data_ligacao)}</span>·<span>{fmtPhone(c.telefone)}</span>·<span>{fmtDur(c.duracao_segundos)}</span>
                {c.id_ligacao && (
                  <>
                    ·
                    <button
                      className="inline-flex items-center gap-1 hover:text-ink"
                      onClick={() => {
                        navigator.clipboard?.writeText(String(c.id_ligacao));
                        toast("ID da ligação copiado");
                      }}
                    >
                      #{c.id_ligacao} <Copy className="h-3 w-3" />
                    </button>
                  </>
                )}
              </p>
            </>
          )}
        </div>
        {c && <PlayButton call={c} queue={queue} />}
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Fechar (Esc)">
          <X className="h-5 w-5" />
        </Button>
      </header>

      <div className="scroll-thin flex-1 space-y-5 overflow-y-auto p-4 sm:p-5">
        {isLoading || !c ? (
          <div className="space-y-3">
            <Skeleton className="h-28" />
            <Skeleton className="h-20" />
            <Skeleton className="h-48" />
          </div>
        ) : (
          <>
            {/* Contraste Argus × IA */}
            <section className="grid grid-cols-[1fr_auto_1fr] items-stretch gap-2">
              <div className="rounded-2xl border border-line p-3">
                <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
                  <UserRound className="h-3.5 w-3.5" /> Operador tabulou
                </div>
                <div className="text-sm font-medium text-ink">{c.tabulacao_operador || "—"}</div>
                <div className="mt-1 truncate text-xs text-ink-muted">{c.operador_nome}</div>
              </div>
              <div className="grid place-items-center">
                <span
                  className={cn(
                    "grid h-8 w-8 place-items-center rounded-full",
                    c.divergencia_tabulacao ? "bg-critical/10 text-critical" : "bg-raised text-ink-muted",
                  )}
                >
                  {c.divergencia_tabulacao ? <AlertTriangle className="h-4 w-4" /> : <ArrowRight className="h-4 w-4" />}
                </span>
              </div>
              <div className={cn("rounded-2xl border p-3", c.divergencia_tabulacao ? "border-critical/40 bg-critical/[.04]" : "border-line")}>
                <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
                  <Bot className="h-3.5 w-3.5" /> IA ouviu
                </div>
                <CategoryBadge code={c.categoria} className="text-sm" />
                <div className="mt-1 truncate text-xs text-ink-muted">{c.subcategoria_label}</div>
              </div>
            </section>
            {c.divergencia_tabulacao && (
              <p className="-mt-2 flex items-start gap-2 rounded-xl bg-critical/[.06] p-3 text-xs text-ink">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-critical" />
                <span>
                  <b className="font-semibold">Divergência:</b> {c.divergencia_detalhe}
                </span>
              </p>
            )}

            {c.erro && (
              <p className="flex items-start gap-2 rounded-xl bg-critical/[.06] p-3 text-xs">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-critical" />
                <span className="break-words">{c.erro}</span>
              </p>
            )}

            {(c.resumo || c.confianca != null) && (
              <section className="space-y-3">
                {c.resumo && <p className="text-sm leading-relaxed text-ink-2">{c.resumo}</p>}
                <div className="grid grid-cols-[auto_1fr] items-center gap-3 text-xs text-ink-muted">
                  Confiança da IA <Meter value={c.confianca} />
                </div>
              </section>
            )}

            {c.evidencia && (
              <blockquote className="relative rounded-2xl bg-raised p-4 pl-10 text-sm italic text-ink">
                <Quote className="absolute left-3 top-4 h-4 w-4 text-ink-muted" />
                {c.evidencia}
              </blockquote>
            )}

            {/* Transcrição */}
            <section>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                <Headphones className="h-4 w-4 text-ink-muted" /> Transcrição
              </h3>
              {c.transcricao_diarizada?.length ? (
                <ol className="space-y-2">
                  {c.transcricao_diarizada.map((t, i) => {
                    const op = t.speaker === "ATENDENTE";
                    const ura = t.speaker === "URA";
                    return (
                      <motion.li
                        key={i}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: Math.min(i * 0.04, 0.4) }}
                        className={cn("flex", op ? "justify-start" : "justify-end")}
                      >
                        <div
                          className={cn(
                            "max-w-[85%] rounded-2xl px-3.5 py-2 text-sm",
                            op && "rounded-bl-md bg-raised text-ink",
                            !op && !ura && "rounded-br-md bg-brand-soft text-ink",
                            ura && "rounded-br-md border border-dashed border-line text-ink-2",
                          )}
                        >
                          <div className="mb-0.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
                            {op ? "Operador" : ura ? "Gravação / URA" : "Cliente"}
                            {t.sentiment === "revoltado" && <Pill tone="critical">revoltado</Pill>}
                          </div>
                          {t.text}
                        </div>
                      </motion.li>
                    );
                  })}
                </ol>
              ) : c.transcricao ? (
                <p className="whitespace-pre-wrap rounded-2xl bg-raised p-4 text-sm leading-relaxed text-ink-2">{c.transcricao}</p>
              ) : (
                <p className="text-sm text-ink-muted">Sem transcrição.</p>
              )}
            </section>

            {/* Metadados */}
            <section>
              <button
                onClick={() => setShowRaw((v) => !v)}
                className="flex w-full items-center justify-between rounded-xl py-2 text-sm font-semibold"
                aria-expanded={showRaw}
              >
                Dados da discadora
                <ChevronDown className={cn("h-4 w-4 transition-transform", showRaw && "rotate-180")} />
              </button>
              <AnimatePresence initial={false}>
                {showRaw && (
                  <motion.dl
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="grid grid-cols-2 gap-x-4 gap-y-3 overflow-hidden pt-2 text-xs"
                  >
                    {[
                      ["Operador", c.operador_nome],
                      ["Equipe", c.tipo_agente ?? c.grupo_origem],
                      ["Tronco", c.tronco],
                      ["Discagem", c.tipo_discagem],
                      ["Desligado por", c.desligado_por ? DESLIG_LABEL[c.desligado_por] ?? c.desligado_por : null],
                      ["Sinalização SIP", c.desligamento_detalhe],
                      ["Tempo de reação", c.tempo_reacao_operador != null ? `${c.tempo_reacao_operador}s` : null],
                      ["Campanha", c.id_campanha],
                      ["Lead", c.nr_lead],
                      ["Tabulação normalizada", c.tabulacao_normalizada ? catLabel(c.tabulacao_normalizada) : null],
                      ["Motor", c.motor],
                      ["Origem", c.origem],
                    ].map(([k, v]) => (
                      <div key={k as string} className="min-w-0">
                        <dt className="text-ink-muted">{k}</dt>
                        <dd className="truncate font-medium text-ink" title={String(v ?? "")}>
                          {v ?? "—"}
                        </dd>
                      </div>
                    ))}
                  </motion.dl>
                )}
              </AnimatePresence>
            </section>

            {c.ligacao_referencia && (
              <div className="rounded-2xl border border-line p-3 text-xs">
                <b className="font-semibold">É o cliente:</b> o titular já se identificou na ligação de{" "}
                {fmtDateTime(c.ligacao_referencia.data_ligacao)} ({catLabel(c.ligacao_referencia.categoria)}).
              </div>
            )}
          </>
        )}
      </div>

      <footer className="flex items-center justify-between gap-2 border-t border-line p-3 sm:p-4">
        <span className="text-[11px] text-ink-muted">Esc fecha · espaço toca/pausa</span>
        <Button variant="soft" size="sm" onClick={() => reprocess.mutate()} loading={reprocess.isPending}>
          <RefreshCw className="h-3.5 w-3.5" /> Reanalisar com IA
        </Button>
      </footer>
    </>
  );
}
