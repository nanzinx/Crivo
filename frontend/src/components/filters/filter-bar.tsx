"use client";

import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { CalendarRange, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Select } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { CATEGORIAS, CAT_LABEL, DESLIG_LABEL, STATUS_LABEL, cn } from "@/lib/utils";
import { PRESETS, activePreset, useFilters } from "./use-filters";

export function FilterBar({ showStatus = false }: { showStatus?: boolean }) {
  const { filters: f, setFilters, reset, active } = useFilters();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState(f.q ?? "");
  const { data: opts } = useQuery({ queryKey: ["options"], queryFn: api.options, staleTime: 60_000 });
  const { data: tax } = useQuery({ queryKey: ["taxonomy"], queryFn: api.taxonomy, staleTime: Infinity });
  const preset = activePreset(f);

  // busca com debounce
  useEffect(() => setQ(f.q ?? ""), [f.q]);
  useEffect(() => {
    const t = setTimeout(() => (q !== (f.q ?? "") ? setFilters({ q }) : undefined), 350);
    return () => clearTimeout(t);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const subs = f.categoria && tax?.[f.categoria] ? Object.entries(tax[f.categoria].subs) : [];
  const dimensoes = Object.keys(f).filter((k) => !["data_inicio", "data_fim", "q"].includes(k)).length;

  return (
    <div className="space-y-3">
      {/* Linha 1: período + busca + botão de filtros */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center">
        <div className="scroll-thin -mx-1 flex items-center gap-1 overflow-x-auto px-1 pb-1 md:pb-0">
          <div className="flex shrink-0 rounded-xl border border-line bg-surface p-1">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                onClick={() => {
                  const [a, b] = p.range();
                  setFilters({ data_inicio: a, data_fim: b });
                }}
                className={cn(
                  "relative h-7 rounded-lg px-3 text-xs font-medium text-ink-2 transition hover:text-ink",
                  preset === p.id && "text-ink",
                )}
              >
                {preset === p.id && (
                  <motion.span layoutId="preset" className="absolute inset-0 rounded-lg bg-raised" transition={{ type: "spring", stiffness: 500, damping: 40 }} />
                )}
                <span className="relative">{p.label}</span>
              </button>
            ))}
          </div>
          <label
            className={cn(
              "flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-line bg-surface px-2.5 text-xs text-ink-2",
              !preset && (f.data_inicio || f.data_fim) && "border-brand/40 bg-brand-soft/40",
            )}
          >
            <CalendarRange className="h-4 w-4 text-ink-muted" />
            <input
              type="date"
              value={f.data_inicio ?? ""}
              onChange={(e) => setFilters({ data_inicio: e.target.value })}
              className="w-[110px] bg-transparent outline-none"
              aria-label="Data inicial"
            />
            <span className="text-ink-muted">→</span>
            <input
              type="date"
              value={f.data_fim ?? ""}
              onChange={(e) => setFilters({ data_fim: e.target.value })}
              className="w-[110px] bg-transparent outline-none"
              aria-label="Data final"
            />
          </label>
        </div>

        <div className="flex flex-1 items-center gap-2">
          <label className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-ink-muted" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Buscar cliente, telefone, operador ou trecho falado…"
              className="h-9 w-full rounded-xl border border-line bg-surface pl-9 pr-3 text-sm outline-none transition placeholder:text-ink-muted focus:border-brand"
            />
          </label>
          <Button onClick={() => setOpen((o) => !o)} variant={open || dimensoes > 0 ? "soft" : "outline"} aria-expanded={open}>
            <SlidersHorizontal className="h-4 w-4" />
            <span className="hidden sm:inline">Filtros</span>
            {dimensoes > 0 && (
              <span className="grid h-5 min-w-5 place-items-center rounded-full bg-brand px-1 text-[10px] font-bold text-white">{dimensoes}</span>
            )}
          </Button>
          {active > 0 && (
            <Button variant="ghost" size="icon" onClick={reset} aria-label="Limpar filtros" title="Limpar filtros">
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Linha 2: dimensões (recolhível) */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="card grid grid-cols-2 gap-3 p-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-5 2xl:grid-cols-10">
              <Select label="Categoria IA" value={f.categoria ?? ""} onChange={(e) => setFilters({ categoria: e.target.value, subcategoria: "" })}>
                <option value="">Todas</option>
                {CATEGORIAS.map((c) => (
                  <option key={c} value={c}>
                    {CAT_LABEL[c]}
                  </option>
                ))}
              </Select>
              <Select label="Subcategoria" value={f.subcategoria ?? ""} disabled={!subs.length} onChange={(e) => setFilters({ subcategoria: e.target.value })}>
                <option value="">Todas</option>
                {subs.map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </Select>
              <Select label="Operador" value={f.operador ?? ""} onChange={(e) => setFilters({ operador: e.target.value })}>
                <option value="">Todos</option>
                {opts?.operadores.map((o) => (
                  <option key={o.nome} value={o.nome}>
                    {o.nome} ({o.total})
                  </option>
                ))}
              </Select>
              <Select label="Tronco" value={f.tronco ?? ""} onChange={(e) => setFilters({ tronco: e.target.value })}>
                <option value="">Todos</option>
                {opts?.troncos.map((o) => (
                  <option key={o.nome} value={o.nome}>
                    {o.nome}
                  </option>
                ))}
              </Select>
              <Select label="Equipe" value={f.tipo_agente ?? ""} onChange={(e) => setFilters({ tipo_agente: e.target.value })}>
                <option value="">Todas</option>
                {opts?.tipos_agente.map((o) => (
                  <option key={o} value={o}>
                    {o.charAt(0) + o.slice(1).toLowerCase()}
                  </option>
                ))}
              </Select>
              <Select label="Discagem" value={f.tipo_discagem ?? ""} onChange={(e) => setFilters({ tipo_discagem: e.target.value })}>
                <option value="">Todas</option>
                {opts?.tipos_discagem.map((o) => (
                  <option key={o} value={o}>
                    {o === "URA" ? "URA" : "Ativo"}
                  </option>
                ))}
              </Select>
              <Select label="Desligado por" value={f.desligado_por ?? ""} onChange={(e) => setFilters({ desligado_por: e.target.value })}>
                <option value="">Todos</option>
                {opts?.desligado_por.map((o) => (
                  <option key={o} value={o}>
                    {DESLIG_LABEL[o] ?? o}
                  </option>
                ))}
              </Select>
              <Select label="Tabulação × IA" value={f.divergencia ?? ""} onChange={(e) => setFilters({ divergencia: e.target.value })}>
                <option value="">Todas</option>
                <option value="true">Divergentes</option>
                <option value="false">Coerentes</option>
              </Select>
              <Select label="Revisão humana" value={f.revisao ?? ""} onChange={(e) => setFilters({ revisao: e.target.value })}>
                <option value="">Todas</option>
                <option value="true">Precisa de revisão</option>
                <option value="false">Sem pendência</option>
              </Select>
              {showStatus && (
                <Select label="Status" value={f.status ?? ""} onChange={(e) => setFilters({ status: e.target.value })}>
                  <option value="">Todos</option>
                  {Object.entries(STATUS_LABEL).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </Select>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
