"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertTriangle, Ear, ChevronLeft, ChevronRight, Download, ListMusic, PhoneIncoming, PhoneOutgoing } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { CallDrawer, PlayButton } from "@/components/calls/call-drawer";
import { FilterBar } from "@/components/filters/filter-bar";
import { useFilters } from "@/components/filters/use-filters";
import { Button, Card, CategoryBadge, Empty, Pill, Skeleton } from "@/components/ui/primitives";
import { api, exportUrl, type Call } from "@/lib/api";
import { DESLIG_LABEL, STATUS_LABEL, cn, fmtDateTime, fmtDur, fmtInt, maskPhone } from "@/lib/utils";

const PAGE_SIZE = 50;

export default function Page() {
  return (
    <Suspense>
      <Ligacoes />
    </Suspense>
  );
}

function Ligacoes() {
  const { filters: f, page, setPage, query } = useFilters();
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [cursor, setCursor] = useState(0);
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["calls", query],
    queryFn: () => api.calls(f, page, PAGE_SIZE),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

  // A ligação aberta fica na URL (?ligacao=123): dá para mandar o link para alguém
  const openId = Number(sp.get("ligacao")) || null;
  const setOpen = useCallback(
    (id: number | null) => {
      const next = new URLSearchParams(sp.toString());
      if (id) next.set("ligacao", String(id));
      else next.delete("ligacao");
      router.replace(`${pathname}?${next}`, { scroll: false });
    },
    [sp, router, pathname],
  );

  const items = data?.items ?? [];
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  // Navegação por teclado: j/k move, Enter abre
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (openId || ["INPUT", "SELECT", "TEXTAREA"].includes(t.tagName)) return;
      if (e.key === "j") setCursor((c) => Math.min(items.length - 1, c + 1));
      else if (e.key === "k") setCursor((c) => Math.max(0, c - 1));
      else if (e.key === "Enter" && items[cursor]) setOpen(items[cursor].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items, cursor, openId, setOpen]);
  useEffect(() => setCursor(0), [query]);

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-1 text-xs font-medium text-ink-muted">
            {data ? `${fmtInt(data.total)} ligações encontradas` : "Carregando…"}
            {isFetching && !isLoading && <span className="ml-2 animate-pulse">· atualizando</span>}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Ligações</h1>
        </div>
        <a href={exportUrl(f)} download>
          <Button variant="primary" size="sm">
            <Download className="h-4 w-4" /> Exportar CSV
          </Button>
        </a>
      </header>

      <FilterBar showStatus />

      <Card className="p-0 sm:p-0">
        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <Empty icon={<ListMusic className="h-5 w-5" />} title="Nenhuma ligação com esses filtros">
            Tente ampliar o período ou limpar os filtros.
          </Empty>
        ) : (
          <>
            {/* Desktop: tabela */}
            <div className="hidden md:block">
              <table className="w-full table-fixed text-sm">
                <thead className="border-b border-line text-left text-[11px] font-medium uppercase tracking-wide text-ink-muted">
                  <tr>
                    <th className="w-14 py-3 pl-4" />
                    <th className="w-[120px] py-3">Quando</th>
                    <th className="py-3">Cliente</th>
                    <th className="hidden w-[150px] py-3 lg:table-cell">Operador</th>
                    <th className="py-3">Tabulação × IA</th>
                    <th className="hidden w-[110px] py-3 xl:table-cell">Desligou</th>
                    <th className="w-[80px] py-3 pr-4 text-right">Duração</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {items.map((c, i) => (
                    <Row key={c.id} c={c} items={items} active={i === cursor} onOpen={() => setOpen(c.id)} index={i} />
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile: cartões */}
            <ul className="divide-y divide-line md:hidden">
              {items.map((c, i) => (
                <motion.li
                  key={c.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: Math.min(i * 0.015, 0.3) }}
                  onClick={() => setOpen(c.id)}
                  className="flex items-start gap-3 p-4 active:bg-raised"
                >
                  <PlayButton call={c} queue={items} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm font-medium">{c.cliente_identificado || c.nome_esperado || "Sem nome"}</span>
                      <span className="num shrink-0 text-[11px] text-ink-muted">{fmtDateTime(c.data_ligacao)}</span>
                    </div>
                    <div className="mt-0.5 truncate text-xs text-ink-muted">
                      {c.operador_nome} · {fmtDur(c.duracao_segundos)}
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {c.categoria && <CategoryBadge code={c.categoria} />}
                      {c.divergencia_tabulacao && (
                        <Pill tone="critical">
                          <AlertTriangle className="h-3 w-3" /> diverge
                        </Pill>
                      )}
                      {c.precisa_revisao && (
                        <Pill tone="warn">
                          <Ear className="h-3 w-3" /> revisar
                        </Pill>
                      )}
                      {c.status !== "done" && <Pill tone={c.status === "error" ? "critical" : "neutral"}>{STATUS_LABEL[c.status]}</Pill>}
                    </div>
                  </div>
                </motion.li>
              ))}
            </ul>
          </>
        )}

        {data && data.total > 0 && (
          <footer className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-xs text-ink-muted">
            <span className="num">
              {fmtInt((page - 1) * PAGE_SIZE + 1)}–{fmtInt(Math.min(page * PAGE_SIZE, data.total))} de {fmtInt(data.total)}
            </span>
            <span className="hidden lg:inline">
              <kbd className="rounded border border-line px-1">j</kbd>/<kbd className="rounded border border-line px-1">k</kbd> navegar ·{" "}
              <kbd className="rounded border border-line px-1">Enter</kbd> abrir · <kbd className="rounded border border-line px-1">espaço</kbd> tocar
            </span>
            <div className="flex items-center gap-1">
              <Button size="icon" variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Página anterior">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="num px-1">
                {page}/{pages}
              </span>
              <Button size="icon" variant="ghost" disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Próxima página">
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </footer>
        )}
      </Card>

      <CallDrawer id={openId} onClose={() => setOpen(null)} queue={items} />
    </div>
  );
}

function Row({ c, items, active, onOpen, index }: { c: Call; items: Call[]; active: boolean; onOpen: () => void; index: number }) {
  return (
    <motion.tr
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: Math.min(index * 0.012, 0.3) }}
      onClick={onOpen}
      className={cn("group cursor-pointer transition-colors hover:bg-raised/60", active && "bg-raised/80")}
    >
      <td className="py-2.5 pl-4">
        <PlayButton call={c} queue={items} size="sm" />
      </td>
      <td className="num py-2.5 text-xs text-ink-2">{fmtDateTime(c.data_ligacao)}</td>
      <td className="py-2.5 pr-3">
        <div className="truncate font-medium text-ink">{c.cliente_identificado || c.nome_esperado || "Sem nome"}</div>
        <div className="num truncate text-xs text-ink-muted">{maskPhone(c.telefone)}</div>
      </td>
      <td className="hidden py-2.5 pr-3 lg:table-cell">
        <div className="truncate text-ink-2">{c.operador_nome}</div>
        <div className="flex items-center gap-1 truncate text-[11px] text-ink-muted">
          {c.tipo_discagem === "URA" ? <PhoneIncoming className="h-3 w-3" /> : <PhoneOutgoing className="h-3 w-3" />}
          {c.tronco ?? "—"}
        </div>
      </td>
      <td className="py-2.5 pr-3">
        <div className="flex items-center gap-2">
          {c.categoria && <CategoryBadge code={c.categoria} sub={c.subcategoria_label !== "-" ? c.subcategoria_label : null} />}
          {c.precisa_revisao && (
            <span title={c.revisao_motivo ?? "Precisa de revisão humana"}>
              <Pill tone="warn">
                <Ear className="h-3 w-3" /> revisar
              </Pill>
            </span>
          )}
          {c.status !== "done" && <Pill tone={c.status === "error" ? "critical" : "neutral"}>{STATUS_LABEL[c.status]}</Pill>}
        </div>
        <div className={cn("mt-0.5 flex items-center gap-1 truncate text-xs", c.divergencia_tabulacao ? "text-critical" : "text-ink-muted")}>
          {c.divergencia_tabulacao && <AlertTriangle className="h-3 w-3 shrink-0" />}
          <span className="truncate">Operador: {c.tabulacao_operador || "—"}</span>
        </div>
      </td>
      <td className="hidden py-2.5 text-xs text-ink-2 xl:table-cell">{c.desligado_por ? DESLIG_LABEL[c.desligado_por] ?? c.desligado_por : "—"}</td>
      <td className="num py-2.5 pr-4 text-right text-xs text-ink-2">{fmtDur(c.duracao_segundos)}</td>
    </motion.tr>
  );
}
