"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ClipboardCheck, Pencil, Undo2, UserCheck, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth-context";
import { Button, CategoryBadge } from "@/components/ui/primitives";
import { api, type Call } from "@/lib/api";
import { CATEGORIAS, catColor, catLabel, cn, fmtDateTime } from "@/lib/utils";

const CHAVE_REVISOR = "crivo.revisor";

function lerRevisor() {
  try {
    return localStorage.getItem(CHAVE_REVISOR) ?? "";
  } catch {
    return "";
  }
}

function salvarRevisor(nome: string) {
  try {
    localStorage.setItem(CHAVE_REVISOR, nome);
  } catch {
    /* navegação privada: só não lembra o nome */
  }
}

/** Revisão humana: confirmar ou corrigir o resultado da IA. Vira o resultado da ligação e o gabarito da medição. */
export function RevisaoPanel({ c }: { c: Call }) {
  const qc = useQueryClient();
  const { data: tax } = useQuery({ queryKey: ["taxonomy"], queryFn: api.taxonomy, staleTime: Infinity });
  const [editando, setEditando] = useState(false);
  const [cat, setCat] = useState(c.categoria ?? "");
  const [sub, setSub] = useState<string>(c.subcategoria ?? "");
  const [obs, setObs] = useState("");
  const { usuario, podeEditar } = useAuth();
  const [revisor, setRevisor] = useState("");
  useEffect(() => setRevisor(usuario?.nome ?? lerRevisor()), [usuario]);

  const pronto = (r: Call, msg: string) => {
    qc.setQueryData(["call", c.id], r);
    qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "call" });
    toast.success(msg);
    setEditando(false);
  };
  const revisar = useMutation({
    mutationFn: (corpo: { categoria: string; subcategoria: string | null; observacao: string | null }) => {
      salvarRevisor(revisor.trim());
      return api.revisar(c.id, { ...corpo, revisor: revisor.trim() });
    },
    onSuccess: (r) => pronto(r, r.ia_acertou === false ? "Correção registrada" : "Resultado confirmado"),
    onError: (e) => toast.error((e as Error).message),
  });
  const desfazer = useMutation({
    mutationFn: () => api.desfazerRevisao(c.id),
    onSuccess: (r) => pronto(r, "Revisão desfeita: vale de novo a resposta da IA"),
    onError: (e) => toast.error((e as Error).message),
  });

  if (c.status !== "done" || !c.categoria) return null;
  if (!podeEditar && !c.revisado) return null;
  const semNome = !revisor.trim();
  const subs = cat && tax?.[cat] ? Object.entries(tax[cat].subs) : [];

  if (c.revisado && !editando) {
    const iaDiferente = c.categoria_ia && c.ia_acertou === false;
    return (
      <section className="rounded-2xl border border-good/30 bg-good/[.05] p-3 text-xs">
        <div className="flex items-start gap-2">
          <UserCheck className="mt-0.5 h-4 w-4 shrink-0 text-good" />
          <div className="min-w-0 flex-1 space-y-1">
            <p className="text-ink">
              <b className="font-semibold">Revisado por {c.revisado_por}</b>
              {c.revisado_em && <span className="text-ink-muted"> · {fmtDateTime(c.revisado_em)}</span>}
            </p>
            {iaDiferente ? (
              <p className="text-ink-2">
                A IA tinha dito <b className="font-medium">{c.categoria_ia_label}</b>
                {c.subcategoria_ia_label ? ` (${c.subcategoria_ia_label})` : ""}; a revisão corrigiu para {catLabel(c.categoria)}.
              </p>
            ) : c.categoria_ia ? (
              <p className="text-ink-2">A revisão confirmou o resultado da IA.</p>
            ) : (
              <p className="text-ink-2">Resultado da escuta manual (sem resposta da IA para comparar ainda).</p>
            )}
            {c.revisao_observacao && <p className="italic text-ink-2">“{c.revisao_observacao}”</p>}
          </div>
          <div className={cn("flex shrink-0 gap-1", !podeEditar && "hidden")}>
            <Button size="sm" variant="ghost" onClick={() => setEditando(true)} title="Alterar a revisão">
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            {c.categoria_ia && (
              <Button size="sm" variant="ghost" onClick={() => desfazer.mutate()} loading={desfazer.isPending} title="Desfazer a revisão">
                <Undo2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-line p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          <ClipboardCheck className="h-4 w-4 text-ink-muted" /> Revisão humana
        </h3>
        {usuario ? (
          <span className="text-xs text-ink-muted">como {usuario.nome}</span>
        ) : (
        <input
          value={revisor}
          onChange={(e) => setRevisor(e.target.value)}
          placeholder="Seu nome"
          aria-label="Nome de quem está revisando"
          className={cn(
            "h-8 w-36 rounded-lg border bg-surface px-2 text-xs outline-none focus:border-brand",
            semNome ? "border-warn" : "border-line",
          )}
        />
        )}
      </div>

      <AnimatePresence initial={false} mode="wait">
        {!editando ? (
          <motion.div key="rapido" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-ink-2">Depois de ouvir, a IA acertou?</span>
            <Button
              size="sm"
              variant="soft"
              disabled={semNome}
              loading={revisar.isPending}
              onClick={() => revisar.mutate({ categoria: c.categoria!, subcategoria: c.subcategoria ?? null, observacao: null })}
            >
              <Check className="h-3.5 w-3.5" /> Sim, está certo
            </Button>
            <Button size="sm" variant="outline" disabled={semNome} onClick={() => setEditando(true)}>
              <X className="h-3.5 w-3.5" /> Não, corrigir
            </Button>
            {semNome && <span className="text-[11px] text-ink-muted">Informe seu nome para revisar.</span>}
          </motion.div>
        ) : (
          <motion.div key="corrigir" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-3">
            <div className="flex flex-wrap gap-1.5">
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
            <textarea
              value={obs}
              onChange={(e) => setObs(e.target.value)}
              placeholder="Observação (opcional): o que a IA não percebeu?"
              rows={2}
              className="w-full resize-none rounded-xl border border-line bg-surface p-2 text-sm outline-none focus:border-brand"
            />
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] text-ink-muted">
                A IA disse <CategoryBadge code={c.categoria_ia ?? c.categoria} className="text-[11px]" />
              </span>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={() => setEditando(false)}>
                  Cancelar
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  disabled={!cat || semNome}
                  loading={revisar.isPending}
                  onClick={() => revisar.mutate({ categoria: cat, subcategoria: sub || null, observacao: obs || null })}
                >
                  Salvar revisão
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
