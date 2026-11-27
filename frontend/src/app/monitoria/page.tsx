"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowRight, ChevronLeft, ChevronRight, ClipboardCheck, Lock, ScrollText, Target } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/components/auth-context";
import { Button, Card, Empty, Pill, Select, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn, fmtDateTime, fmtDur, fmtInt } from "@/lib/utils";

export default function MonitoriaPage() {
  const { podeAvaliar } = useAuth();
  const [operador, setOperador] = useState("");
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({
    queryKey: ["fila", operador, page],
    queryFn: () => api.fila({ operador: operador || undefined, page }),
    refetchInterval: 20_000,
  });
  const { data: opts } = useQuery({ queryKey: ["options"], queryFn: api.options, staleTime: 300_000 });
  const meta = data?.meta;
  const pct = meta && meta.diaria ? Math.min(100, (100 * meta.feitas_hoje) / meta.diaria) : 0;
  const paginas = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs text-ink-muted">Monitoria de qualidade</p>
          <h1 className="text-2xl font-semibold tracking-tight">Fila de avaliação</h1>
        </div>
        <Link href="/script" className="inline-flex items-center gap-1.5 text-sm font-medium text-brand-ink hover:underline">
          <ScrollText className="h-4 w-4" /> Ver o script de vendas
        </Link>
      </header>

      <section className="grid gap-3 sm:grid-cols-3">
        <div className="card flex items-center gap-3 p-4">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-warn/15 text-ink">
            <ClipboardCheck className="h-5 w-5" />
          </span>
          <div>
            <div className="num text-2xl font-semibold">{data ? fmtInt(data.total) : "–"}</div>
            <div className="text-xs text-ink-muted">ligações aguardando avaliação</div>
          </div>
        </div>
        <div className="card p-4 sm:col-span-2">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="flex items-center gap-1.5 font-medium">
              <Target className="h-4 w-4 text-ink-muted" /> Sua meta de hoje
            </span>
            <span className="num text-ink-2">
              {meta ? `${fmtInt(meta.feitas_hoje)} de ${fmtInt(meta.diaria)}` : "–"}
            </span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-raised" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
            <motion.div
              className={cn("h-full rounded-full", pct >= 100 ? "bg-good" : "bg-brand")}
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.6 }}
            />
          </div>
          <p className="mt-2 text-xs text-ink-muted">Avaliações finalizadas ou marcadas como não avaliáveis hoje.</p>
        </div>
      </section>

      <Card
        title="Ligações para ouvir"
        subtitle="Mais antigas primeiro. Quem está avaliando trava a ligação por 15 minutos."
        action={
          <Select
            aria-label="Operador"
            value={operador}
            onChange={(e) => {
              setOperador(e.target.value);
              setPage(1);
            }}
            className="w-48"
          >
            <option value="">Todos os operadores</option>
            {opts?.operadores.map((o) => (
              <option key={o.nome} value={o.nome}>
                {o.nome}
              </option>
            ))}
          </Select>
        }
      >
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : !data?.itens.length ? (
          <Empty icon={<ClipboardCheck className="h-5 w-5" />} title="Fila vazia">
            Nenhuma ligação aguardando avaliação{operador ? " para este operador" : ""}.
          </Empty>
        ) : (
          <ul className="divide-y divide-line">
            {data.itens.map((c, i) => {
              const ocupada = c.rascunho?.trava && !c.rascunho.minha;
              return (
                <motion.li
                  key={c.id}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.02, 0.3) }}
                  className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium">{c.operador_nome ?? "Operador não identificado"}</span>
                      {c.grupo && <span className="text-xs text-ink-muted">{c.grupo}</span>}
                      {c.rascunho &&
                        (c.rascunho.minha ? (
                          <Pill tone="brand">seu rascunho</Pill>
                        ) : c.rascunho.trava ? (
                          <Pill tone="warn">
                            <Lock className="h-3 w-3" /> {c.rascunho.trava} avaliando
                          </Pill>
                        ) : (
                          <Pill>rascunho de {c.rascunho.monitora}</Pill>
                        ))}
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-ink-muted">
                      <span className="num">{fmtDateTime(c.data_ligacao)}</span>·<span className="num">{fmtDur(c.duracao_segundos)}</span>·
                      <span className="truncate">Tabulou: {c.tabulacao_operador || "—"}</span>
                    </div>
                  </div>
                  {podeAvaliar && (
                    <Link href={`/monitoria/avaliar/${c.id}`} aria-disabled={!!ocupada} tabIndex={ocupada ? -1 : undefined} className={cn(ocupada && "pointer-events-none")}>
                      <Button size="sm" variant={c.rascunho?.minha ? "primary" : "soft"} disabled={!!ocupada}>
                        {c.rascunho?.minha ? "Continuar" : "Avaliar"} <ArrowRight className="h-3.5 w-3.5" />
                      </Button>
                    </Link>
                  )}
                </motion.li>
              );
            })}
          </ul>
        )}
        {data && paginas > 1 && (
          <div className="mt-3 flex items-center justify-end gap-2 text-xs text-ink-muted">
            <Button size="icon" variant="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="Página anterior">
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="num">
              {page} / {paginas}
            </span>
            <Button size="icon" variant="ghost" disabled={page >= paginas} onClick={() => setPage((p) => p + 1)} aria-label="Próxima página">
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
