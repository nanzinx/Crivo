"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import type { Filters } from "@/lib/api";
import { isoDate } from "@/lib/utils";

const KEYS: (keyof Filters)[] = [
  "data_inicio",
  "data_fim",
  "categoria",
  "subcategoria",
  "tronco",
  "operador",
  "tipo_agente",
  "tipo_discagem",
  "desligado_por",
  "divergencia",
  "revisao",
  "status",
  "q",
];

/** Filtros vivem na URL: dá para compartilhar o link de uma visão filtrada. */
export function useFilters() {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const filters = useMemo(() => {
    const f: Filters = {};
    for (const k of KEYS) {
      const v = sp.get(k);
      if (v) f[k] = v;
    }
    return f;
  }, [sp]);

  const page = Number(sp.get("page") || 1);

  const replace = useCallback(
    (next: URLSearchParams) => {
      const s = next.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    },
    [router, pathname],
  );

  const setFilters = useCallback(
    (patch: Partial<Filters>) => {
      const next = new URLSearchParams(sp.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined || v === null || v === "") next.delete(k);
        else next.set(k, String(v));
      }
      next.delete("page");
      replace(next);
    },
    [sp, replace],
  );

  const setPage = useCallback(
    (p: number) => {
      const next = new URLSearchParams(sp.toString());
      if (p <= 1) next.delete("page");
      else next.set("page", String(p));
      replace(next);
    },
    [sp, replace],
  );

  const reset = useCallback(() => replace(new URLSearchParams()), [replace]);

  const active = KEYS.filter((k) => filters[k]).length;
  return { filters, setFilters, page, setPage, reset, active, query: sp.toString() };
}

export type Preset = { id: string; label: string; range: () => [string, string] };

const daysAgo = (n: number) => isoDate(new Date(Date.now() - n * 864e5));

export const PRESETS: Preset[] = [
  { id: "hoje", label: "Hoje", range: () => [daysAgo(0), daysAgo(0)] },
  { id: "ontem", label: "Ontem", range: () => [daysAgo(1), daysAgo(1)] },
  { id: "7d", label: "7 dias", range: () => [daysAgo(6), daysAgo(0)] },
  { id: "30d", label: "30 dias", range: () => [daysAgo(29), daysAgo(0)] },
  { id: "tudo", label: "Tudo", range: () => ["", ""] },
];

export function activePreset(f: Filters): string | null {
  for (const p of PRESETS) {
    const [a, b] = p.range();
    if ((f.data_inicio || "") === a && (f.data_fim || "") === b) return p.id;
  }
  return null;
}
