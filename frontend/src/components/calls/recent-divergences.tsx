"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useFilters } from "@/components/filters/use-filters";
import { Card, CategoryBadge, Empty, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { fmtDateTime, fmtDur } from "@/lib/utils";
import { CallDrawer, PlayButton } from "./call-drawer";

/** Fila de revisão rápida: as divergências mais recentes dentro dos filtros atuais. */
export function RecentDivergences() {
  const { filters, query } = useFilters();
  const f = { ...filters, divergencia: "true" };
  const [open, setOpen] = useState<number | null>(null);
  const { data } = useQuery({
    queryKey: ["recent-div", query],
    queryFn: () => api.calls(f, 1, 8),
    refetchInterval: 30_000,
  });
  const params = new URLSearchParams(query);
  params.set("divergencia", "true");

  return (
    <Card
      title="Para revisar agora"
      subtitle="Divergências mais recentes entre a tabulação e a gravação"
      action={
        <Link href={`/ligacoes?${params}`} className="inline-flex items-center gap-1 text-xs font-medium text-brand-ink hover:underline">
          Ver todas <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      }
    >
      {!data ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[74px]" />
          ))}
        </div>
      ) : data.items.length === 0 ? (
        <Empty title="Nenhuma divergência no período 🎉" />
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {data.items.map((c, i) => (
            <motion.li
              key={c.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
            >
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
                    <span className="truncate text-sm font-medium">{c.operador_nome}</span>
                    <span className="num shrink-0 text-[11px] text-ink-muted">
                      {fmtDateTime(c.data_ligacao)} · {fmtDur(c.duracao_segundos)}
                    </span>
                  </div>
                  <div className="mt-1 flex min-w-0 items-center gap-2 text-xs">
                    <span className="truncate text-ink-2 line-through decoration-critical/60">{c.tabulacao_operador}</span>
                    <ArrowRight className="h-3 w-3 shrink-0 text-ink-muted" />
                    <CategoryBadge code={c.categoria} />
                  </div>
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
