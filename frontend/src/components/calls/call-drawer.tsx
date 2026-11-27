"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ClipboardCheck,
  Copy,
  Ear,
  Pause,
  Play,
  RefreshCw,
  UserCheck,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { usePlayer } from "@/components/player/player-context";
import { ResultadoPanel } from "./resultado-panel";
import { Button, CategoryBadge, GravidadePill, NaoLigarPill, Pill, Skeleton } from "@/components/ui/primitives";
import { api, type Call } from "@/lib/api";
import { DESLIG_LABEL, STATUS_LABEL, catLabel, cn, fmtDateTime, fmtDur, fmtPhone } from "@/lib/utils";
import { useAuth } from "@/components/auth-context";

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
  const { podeEditar } = useAuth();
  const baixar = useMutation({
    mutationFn: () => api.baixarAudioDeNovo(id),
    onSuccess: (r) => {
      toast.success(r.enfileirada ? "Gravação na fila para baixar de novo" : "A gravação já está na fila");
      setTimeout(() => qc.invalidateQueries({ queryKey: ["call", id] }), 2500);
    },
    onError: (e) => toast.error(`Falha ao pedir o download: ${(e as Error).message}`),
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
                {c.status !== "avaliada" && <Pill tone={c.status === "erro" ? "critical" : c.status === "nao_avaliavel" ? "warn" : "neutral"}>{STATUS_LABEL[c.status] ?? c.status}</Pill>}
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
            {/* Contraste: o que o operador tabulou × o que a monitora avaliou */}
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
                  {c.avaliado_por ? <UserCheck className="h-3.5 w-3.5" /> : <ClipboardCheck className="h-3.5 w-3.5" />} Monitoria
                </div>
                {c.categoria ? (
                  <CategoryBadge code={c.categoria} className="text-sm" />
                ) : (
                  <div className="text-sm text-ink-muted">{c.status === "nao_avaliavel" ? "Não avaliável" : "Aguardando avaliação"}</div>
                )}
                {c.subcategoria_label && c.subcategoria_label !== "-" && (
                  <div className="mt-1 truncate text-xs text-ink-muted">{c.subcategoria_label}</div>
                )}
              </div>
            </section>
            {c.divergencia_tabulacao && (
              <div className="-mt-2 flex items-start gap-2 rounded-xl bg-critical/[.06] p-3 text-xs text-ink">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-critical" />
                <div className="space-y-1.5">
                  <p className="flex flex-wrap items-center gap-2">
                    <b className="font-semibold">Divergência</b> <GravidadePill g={c.divergencia_gravidade} />
                  </p>
                  <p>{c.divergencia_detalhe}</p>
                  {c.tabulacao_confirmada === false && (
                    <p className="text-ink-muted">
                      O significado desta tabulação ainda é só uma sugestão do sistema.{" "}
                      <Link href="/tabulacoes" className="font-medium text-brand-ink underline">
                        Confirmar em Modelo de tabulação
                      </Link>
                    </p>
                  )}
                </div>
              </div>
            )}

            {c.pediu_nao_ligar && (
              <p className="-mt-2 flex items-start gap-2 rounded-xl bg-brand-soft p-3 text-xs text-ink">
                <NaoLigarPill className="shrink-0 bg-surface" />
                <span>Quem atendeu pediu para não receber mais ligações. Confira se o número saiu do mailing.</span>
              </p>
            )}

            {c.status === "pendente_avaliacao" && (
              <p className="-mt-2 flex items-start gap-2 rounded-xl bg-warn/15 p-3 text-xs text-ink">
                <Ear className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  <b className="font-semibold">Aguardando avaliação da monitoria.</b> Enquanto ninguém ouvir, esta ligação não conta como
                  divergência do operador.
                </span>
              </p>
            )}

            <ResultadoPanel c={c} />

            {c.erro && (
              <p className="flex items-start gap-2 rounded-xl bg-critical/[.06] p-3 text-xs">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-critical" />
                <span className="break-words">{c.erro}</span>
              </p>
            )}

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
        {podeEditar && (
          <Button variant="soft" size="sm" onClick={() => baixar.mutate()} loading={baixar.isPending} title="Baixa a gravação do Argus de novo (não desfaz a avaliação)">
            <RefreshCw className="h-3.5 w-3.5" /> Baixar áudio de novo
          </Button>
        )}
      </footer>
    </>
  );
}
