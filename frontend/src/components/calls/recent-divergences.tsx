"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertTriangle, ArrowRight, Ear, PhoneOff } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useFilters } from "@/components/filters/use-filters";
import { Card, CategoryBadge, Empty, GravidadePill, NaoLigarPill, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { cn, fmtDateTime, fmtDur } from "@/lib/utils";
import { CallDrawer, PlayButton } from "./call-drawer";

type Aba = "divergencia" | "revisao" | "nao_ligar";

/** Fila de trabalho do supervisor: divergências apontadas pela monitoria e ligações aguardando avaliação. */
export function RecentDivergences() {
  const { filters, query } = useFilters();
  const [aba, setAba] = useState<Aba>("divergencia");
  const [open, setOpen] = useState<number | null>(null);
  const f = { ...filters, [aba]: "true" };
  const { data } = useQuery({
    queryKey: ["recentes", aba, query],
    queryFn: () => api.calls(f, 1, 8, aba === "divergencia" ? "gravidade" : undefined),
    refetchInterval: 30_000,
  });
  const params = new URLSearchParams(query);
  params.set(aba, "true");

  return (
    <Card
      title="Para olhar agora"
      subtitle={
        aba === "divergencia"
          ? "A avaliação da monitoria não bate com a tabulação do operador · mais graves primeiro"
          : aba === "revisao"
            ? "Gravações prontas, esperando a monitoria ouvir"
            : "Quem atendeu pediu para não receber mais ligações (LGPD): confira se o número saiu do mailing"
      }
      action={
        <Link href={`/ligacoes?${params}`} className="inline-flex items-center gap-1 text-xs font-medium text-brand-ink hover:underline">
          Ver todas <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      }
    >
      <div className="mb-3 flex w-fit rounded-xl bg-raised p-1 text-xs" role="tablist">
        {(
          [
            ["divergencia", "Divergências", AlertTriangle],
            ["revisao", "Aguardando avaliação", Ear],
            ["nao_ligar", "Não ligar", PhoneOff],
          ] as const
        ).map(([id, label, Icon]) => (
          <button
            key={id}
            role="tab"
            aria-selected={aba === id}
            onClick={() => setAba(id)}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-medium text-ink-muted transition",
              aba === id && "bg-surface text-ink shadow-sm",
            )}
          >
            <Icon className="h-3.5 w-3.5" /> {label}
          </button>
        ))}
      </div>

      {!data ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[74px]" />
          ))}
        </div>
      ) : data.items.length === 0 ? (
        <Empty
          title={
            aba === "divergencia" ? "Nenhuma divergência no período 🎉" : aba === "revisao" ? "Nada aguardando avaliação" : "Nenhum pedido de não ligar no período"
          }
        />
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {data.items.map((c, i) => (
            <motion.li key={c.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <div
                role="button"
                tabIndex={0}
                onClick={() => setOpen(c.id)}
                onKeyDown={(e) => e.key === "Enter" && setOpen(c.id)}
                className="flex cursor-pointer items-center gap-3 rounded-2xl border border-line p-3 transition hover:border-ink/20 hover:bg-raised/50"
              >
                <PlayButton call={c} queue={data.items} size="sm" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="truncate text-sm font-medium">{c.operador_nome}</span>
                      {aba === "divergencia" && <GravidadePill g={c.divergencia_gravidade} />}
                    </span>
                    <span className="num shrink-0 text-[11px] text-ink-muted">
                      {fmtDateTime(c.data_ligacao)} · {fmtDur(c.duracao_segundos)}
                    </span>
                  </div>
                  {aba !== "revisao" ? (
                    <div className="mt-1 flex min-w-0 items-center gap-2 text-xs">
                      <span className={cn("truncate text-ink-2", aba === "divergencia" && "line-through decoration-critical/60")}>
                        {c.tabulacao_operador}
                      </span>
                      <ArrowRight className="h-3 w-3 shrink-0 text-ink-muted" />
                      <CategoryBadge code={c.categoria} />
                      {c.pediu_nao_ligar && aba === "divergencia" && <NaoLigarPill className="shrink-0" />}
                    </div>
                  ) : (
                    <div className="mt-1 truncate text-xs text-ink-2">Operador tabulou: {c.tabulacao_operador || "—"}</div>
                  )}
                </div>
              </div>
            </motion.li>
          ))}
        </ul>
      )}
      <CallDrawer id={open} onClose={() => setOpen(null)} queue={data?.items} />
    </Card>
  );
}
