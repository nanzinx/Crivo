"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Ban, ClipboardCheck, Pencil, UserCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth-context";
import { Button, CategoryBadge, NaoLigarPill } from "@/components/ui/primitives";
import { api, type Call, type ResultadoIn } from "@/lib/api";
import { CATEGORIAS, catColor, catLabel, cn, fmtDateTime } from "@/lib/utils";

/**
 * Resultado da ligação, registrado pela monitoria de qualidade depois de ouvir a gravação.
 * Vira o resultado oficial e entra na comparação com a tabulação do operador.
 * Supervisores e leitura só veem o que foi registrado.
 */
export function ResultadoPanel({ c }: { c: Call }) {
  const qc = useQueryClient();
  const { podeAvaliar } = useAuth();
  const { data: tax } = useQuery({ queryKey: ["taxonomy"], queryFn: api.taxonomy, staleTime: Infinity });
  const finalizada = c.status === "avaliada" || c.status === "nao_avaliavel";
  const [editando, setEditando] = useState(false);
  const [cat, setCat] = useState(c.categoria ?? "");
  const [sub, setSub] = useState(c.subcategoria ?? "");
  const [naoLigar, setNaoLigar] = useState(Boolean(c.pediu_nao_ligar));
  const [naoAvaliavel, setNaoAvaliavel] = useState(c.status === "nao_avaliavel");
  const [motivo, setMotivo] = useState(c.avaliacao?.nao_avaliavel_motivo ?? "");

  const salvar = useMutation({
    mutationFn: (r: ResultadoIn) => api.registrarResultado(c.id, r),
    onSuccess: (r) => {
      qc.setQueryData(["call", c.id], r);
      qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "call" });
      toast.success(r.status === "nao_avaliavel" ? "Marcada como não avaliável" : "Resultado registrado");
      setEditando(false);
    },
    onError: (e) => toast.error((e as Error).message),
  });

  if (!finalizada && !podeAvaliar) return null;
  const subs = cat && tax?.[cat] ? Object.entries(tax[cat].subs) : [];

  if (finalizada && !editando) {
    return (
      <section className="flex items-start gap-3 rounded-2xl border border-line p-3 text-xs">
        <UserCheck className="mt-0.5 h-4 w-4 shrink-0 text-ok" />
        <div className="min-w-0 flex-1 space-y-1">
          <p>
            <b className="font-semibold">{c.status === "nao_avaliavel" ? "Não avaliável" : "Avaliada"}</b>
            {c.avaliado_por && <> por {c.avaliado_por}</>}
            {c.avaliado_em && <span className="text-ink-muted"> · {fmtDateTime(c.avaliado_em)}</span>}
          </p>
          {c.status === "nao_avaliavel" ? (
            <p className="text-ink-2">{c.avaliacao?.nao_avaliavel_motivo ?? "Sem motivo informado."}</p>
          ) : (
            <p className="flex flex-wrap items-center gap-1.5 text-ink-2">
              <CategoryBadge code={c.categoria} className="text-[11px]" />
              {c.subcategoria_label && c.subcategoria_label !== "-" && <span>{c.subcategoria_label}</span>}
              {c.pediu_nao_ligar && <NaoLigarPill />}
            </p>
          )}
        </div>
        {podeAvaliar && (
          <Button size="sm" variant="ghost" onClick={() => setEditando(true)} title="Corrigir o resultado">
            <Pencil className="h-3.5 w-3.5" /> Corrigir
          </Button>
        )}
      </section>
    );
  }

  const podeSalvar = naoAvaliavel ? motivo.trim().length > 0 : Boolean(cat);
  return (
    <section className="space-y-3 rounded-2xl border border-line p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          <ClipboardCheck className="h-4 w-4 text-ink-muted" /> Resultado da ligação
        </h3>
        <button
          type="button"
          aria-pressed={naoAvaliavel}
          onClick={() => setNaoAvaliavel((v) => !v)}
          className={cn(
            "inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] transition",
            naoAvaliavel ? "border-warn bg-warn/15 font-medium text-ink" : "border-line text-ink-muted hover:text-ink",
          )}
        >
          <Ban className="h-3 w-3" /> Não dá para avaliar
        </button>
      </div>

      <AnimatePresence initial={false} mode="wait">
        {naoAvaliavel ? (
          <motion.div key="na" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <textarea
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Por quê? (áudio cortado, sem som, gravação de outra ligação...)"
              rows={2}
              aria-label="Motivo de não ser avaliável"
              className="w-full resize-none rounded-xl border border-line bg-surface p-2 text-sm outline-none focus:border-brand"
            />
          </motion.div>
        ) : (
          <motion.div key="res" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-3">
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Categoria">
              {CATEGORIAS.map((k) => (
                <button
                  key={k}
                  type="button"
                  aria-pressed={cat === k}
                  onClick={() => {
                    setCat(k);
                    setSub("");
                  }}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition",
                    cat === k ? "border-ink/40 bg-surface font-medium text-ink shadow-sm" : "border-line text-ink-muted hover:text-ink",
                  )}
                >
                  <span className="h-2 w-2 rounded-full" style={{ background: catColor(k) }} />
                  {catLabel(k)}
                </button>
              ))}
            </div>
            {subs.length > 0 && (
              <select
                value={sub}
                onChange={(e) => setSub(e.target.value)}
                className="h-9 w-full rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
                aria-label="Subcategoria"
              >
                <option value="">Subcategoria (opcional)</option>
                {subs.map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            )}
            <label className="flex items-center gap-2 text-xs text-ink-2">
              <input type="checkbox" checked={naoLigar} onChange={(e) => setNaoLigar(e.target.checked)} className="accent-brand" />
              Quem atendeu pediu para não ligar mais
            </label>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex justify-end gap-2">
        {editando && (
          <Button size="sm" variant="ghost" onClick={() => setEditando(false)}>
            Cancelar
          </Button>
        )}
        <Button
          size="sm"
          variant="primary"
          disabled={!podeSalvar}
          loading={salvar.isPending}
          onClick={() =>
            salvar.mutate(
              naoAvaliavel
                ? { nao_avaliavel: true, motivo: motivo.trim() }
                : { categoria: cat, subcategoria: sub || null, pediu_nao_ligar: naoLigar },
            )
          }
        >
          Salvar resultado
        </Button>
      </div>
    </section>
  );
}
