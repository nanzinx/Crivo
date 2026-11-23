"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertOctagon,
  ArrowRight,
  Check,
  CheckCircle2,
  Download,
  ListChecks,
  PhoneOff,
  Search,
  Sparkles,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth-context";
import { Button, Card, Empty, Pill, Skeleton } from "@/components/ui/primitives";
import { api, exportTabulacoesUrl, type RegraTabulacao, type Tabulacao, type TabulacoesResp, type TipoTabulacao } from "@/lib/api";
import { CATEGORIAS, catColor, cn, fmtInt, fmtPct } from "@/lib/utils";

type Aba = "pendentes" | "todas" | "confirmadas";

export default function TabulacoesPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["tabulacoes"], queryFn: api.tabulacoes });
  const [aba, setAba] = useState<Aba>("pendentes");
  const [busca, setBusca] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const importar = useMutation({
    mutationFn: (f: File) => api.importarTabulacoes(f),
    onSuccess: (r) => {
      if (r.erros.length) {
        toast.warning(`${r.importadas} tabulações importadas, ${r.erros.length} com erro`, {
          description: r.erros.slice(0, 4).join("\n") + (r.erros.length > 4 ? "\n…" : ""),
          duration: 12000,
        });
      } else {
        toast.success(`${r.importadas} tabulações importadas`, { description: `${r.mudaram} de ${r.recalculadas} ligações mudaram de resultado` });
      }
      qc.invalidateQueries();
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const itens = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (data?.itens ?? []).filter(
      (t) =>
        (aba === "todas" || (aba === "pendentes" ? !t.confirmada : t.confirmada)) &&
        (!q || t.nome.toLowerCase().includes(q) || String(t.id_argus ?? "").includes(q)),
    );
  }, [data, aba, busca]);

  const r = data?.resumo;
  const pctConfirmado = r && r.total ? (100 * r.confirmadas) / r.total : 0;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-2xl">
          <p className="mb-1 flex items-center gap-2 text-xs font-medium text-ink-muted">
            <ListChecks className="h-3.5 w-3.5 text-brand" /> O que cada tabulação do Argus significa
          </p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Modelo de tabulação</h1>
          <p className="mt-2 text-sm text-ink-2">
            Cada tabulação nova entra aqui com um significado <b className="font-medium">sugerido</b> pelo texto. Confirme ou corrija: é
            esta regra que decide se o operador tabulou certo. Ao salvar, as ligações daquela tabulação são recalculadas.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <a href={exportTabulacoesUrl} download>
            <Button variant="outline" size="sm">
              <Download className="h-4 w-4" /> Exportar planilha
            </Button>
          </a>
          <Button variant="primary" size="sm" onClick={() => fileRef.current?.click()} loading={importar.isPending}>
            <Upload className="h-4 w-4" /> Importar planilha
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) importar.mutate(f);
              e.target.value = "";
            }}
          />
        </div>
      </header>

      {isLoading || !data ? (
        <div className="space-y-3">
          <Skeleton className="h-24" />
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : (
        <>
          <section className="grid gap-3 md:grid-cols-3">
            <div className="card p-4">
              <div className="flex items-baseline justify-between">
                <span className="text-xs font-medium text-ink-2">Confirmadas</span>
                <span className="num text-xs text-ink-muted">{fmtPct(pctConfirmado, 0)}</span>
              </div>
              <div className="mt-1 text-2xl font-semibold tracking-tight">
                {fmtInt(r!.confirmadas)} <span className="text-base font-normal text-ink-muted">de {fmtInt(r!.total)}</span>
              </div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-raised">
                <motion.div className="h-full rounded-full bg-good" initial={{ width: 0 }} animate={{ width: `${pctConfirmado}%` }} />
              </div>
            </div>
            <div className={cn("card p-4", r!.pendentes > 0 && "border-warn/50 bg-warn/[.06]")}>
              <span className="text-xs font-medium text-ink-2">Para confirmar</span>
              <div className="mt-1 text-2xl font-semibold tracking-tight">{fmtInt(r!.pendentes)}</div>
              <p className="mt-1 text-xs text-ink-muted">
                {r!.pendentes ? `${fmtInt(r!.ligacoes_pendentes)} ligações usam um significado só sugerido` : "Todas as tabulações em uso estão confirmadas"}
              </p>
            </div>
            <div className="card p-4">
              <span className="flex items-center gap-1.5 text-xs font-medium text-ink-2">
                <PhoneOff className="h-3.5 w-3.5" /> Pedido de não ligar (LGPD)
              </span>
              <div className="mt-1 text-sm font-medium">{r!.nao_ligar_registrado ? "Há tabulação para registrar" : "Nenhuma tabulação registra"}</div>
              <p className="mt-1 text-xs text-ink-muted">
                {r!.nao_ligar_registrado
                  ? "Pedido feito na ligação e não tabulado assim vira divergência alta."
                  : "Os pedidos aparecem nas listas, mas não contam contra o operador. Marque a tabulação certa abaixo."}
              </p>
            </div>
          </section>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="flex w-fit rounded-xl border border-line bg-surface p-1" role="tablist">
              {(
                [
                  ["pendentes", `Para confirmar (${r!.total - r!.confirmadas})`],
                  ["confirmadas", `Confirmadas (${r!.confirmadas})`],
                  ["todas", "Todas"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  role="tab"
                  aria-selected={aba === id}
                  onClick={() => setAba(id)}
                  className={cn("relative h-7 rounded-lg px-3 text-xs font-medium text-ink-2", aba === id && "text-ink")}
                >
                  {aba === id && <motion.span layoutId="aba-tab" className="absolute inset-0 rounded-lg bg-raised" />}
                  <span className="relative">{label}</span>
                </button>
              ))}
            </div>
            <label className="relative flex-1 sm:max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-ink-muted" />
              <input
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                placeholder="Buscar tabulação ou código do Argus…"
                className="h-9 w-full rounded-xl border border-line bg-surface pl-9 pr-3 text-sm outline-none focus:border-brand"
              />
            </label>
          </div>

          {itens.length === 0 ? (
            <Card>
              <Empty icon={<CheckCircle2 className="h-5 w-5 text-good" />} title={aba === "pendentes" ? "Nada para confirmar" : "Nenhuma tabulação encontrada"}>
                {aba === "pendentes"
                  ? "Todas as tabulações têm significado confirmado. Novas tabulações aparecem aqui automaticamente."
                  : "As tabulações aparecem quando chegam ligações do Argus ou do relatório da discadora."}
              </Empty>
            </Card>
          ) : (
            <ul className="flex flex-col gap-3">
              <AnimatePresence initial={false}>
                {itens.map((t) => (
                  <motion.li key={t.id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}>
                    <Editor key={`${t.id}-${t.atualizado_em ?? ""}`} t={t} opcoes={data.opcoes} />
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          )}

          <details className="card p-4 text-sm text-ink-2">
            <summary className="cursor-pointer font-medium text-ink">Como funciona a planilha</summary>
            <div className="mt-3 space-y-2 text-xs leading-relaxed">
              <p>
                Colunas: <code className="font-mono">tabulacao</code> (texto como no Argus), <code className="font-mono">tipo</code> (resultado,
                nao_tabulado ou ignorar), <code className="font-mono">categorias</code> (uma ou mais, separadas por <code className="font-mono">|</code>),{" "}
                <code className="font-mono">subcategoria</code> (opcional), <code className="font-mono">nao_ligar</code> (sim/não) e, se tiver,{" "}
                <code className="font-mono">id_argus</code>.
              </p>
              <p>Categorias e subcategorias podem vir pelo nome ("Em Negociação") ou pelo código ("EM_NEGOCIACAO"). Exporte a planilha atual para usar de modelo.</p>
              <p>Linhas com erro são listadas ao importar e não alteram nada. As linhas válidas ficam confirmadas.</p>
            </div>
          </details>
        </>
      )}
    </div>
  );
}

const TIPO_AJUDA: Record<TipoTabulacao, string> = {
  resultado: "A tabulação afirma o que aconteceu. Marque as categorias da IA que concordam com ela.",
  nao_tabulado: "O operador não registrou resultado (ex.: tempo pós-atendimento). Diverge se a IA ouviu uma conversa.",
  ignorar: "Não serve para comparar (tabulação de sistema, pausa…). Nunca gera divergência.",
};

function Editor({ t, opcoes }: { t: Tabulacao; opcoes: TabulacoesResp["opcoes"] }) {
  const qc = useQueryClient();
  const { podeEditar } = useAuth();
  const inicial: RegraTabulacao = { tipo: t.tipo, categorias: t.categorias, subcategoria: t.subcategoria, nao_ligar: t.nao_ligar };
  const [r, setR] = useState<RegraTabulacao>(inicial);
  const alterado = JSON.stringify(r) !== JSON.stringify(inicial);
  const invalido = r.tipo === "resultado" && r.categorias.length === 0;
  const subs = r.categorias.flatMap((c) => Object.entries(opcoes.categorias[c]?.subs ?? {}).map(([k, v]) => ({ c, k, v })));

  const salvar = useMutation({
    mutationFn: () => api.salvarTabulacao(t.id, r),
    onSuccess: (res) => {
      toast.success(`"${t.nome}" ${t.confirmada ? "atualizada" : "confirmada"}`, {
        description: res.recalculadas ? `${res.mudaram} de ${res.recalculadas} ligações mudaram de resultado` : undefined,
      });
      qc.invalidateQueries();
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const toggleCat = (c: string) =>
    setR((x) => {
      const categorias = x.categorias.includes(c) ? x.categorias.filter((y) => y !== c) : [...x.categorias, c];
      const sub = x.subcategoria && categorias.some((cc) => x.subcategoria! in (opcoes.categorias[cc]?.subs ?? {})) ? x.subcategoria : null;
      return { ...x, categorias, subcategoria: sub };
    });

  return (
    <div className={cn("card p-4 sm:p-5", !t.confirmada && "border-l-4 border-l-warn")}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-base font-semibold tracking-tight">{t.nome}</h2>
            {t.confirmada ? (
              <Pill tone="good">
                <Check className="h-3 w-3" /> Confirmada
              </Pill>
            ) : (
              <Pill tone="warn">
                <Sparkles className="h-3 w-3" /> Sugerida
              </Pill>
            )}
            {t.id_argus != null && <span className="num text-xs text-ink-muted">cód. Argus {t.id_argus}</span>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
            <span className="num">{fmtInt(t.ligacoes)} ligações</span>
            {t.qualificadas > 0 && (
              <span className="num">
                {fmtPct(t.taxa_divergencia)} divergentes ({fmtInt(t.divergencias)})
              </span>
            )}
            {t.divergencias_altas > 0 && (
              <span className="num inline-flex items-center gap-1 text-critical">
                <AlertOctagon className="h-3 w-3" /> {fmtInt(t.divergencias_altas)} de gravidade alta
              </span>
            )}
            {t.ligacoes > 0 && (
              <Link href={`/ligacoes?q=${encodeURIComponent(t.nome)}`} className="inline-flex items-center gap-1 font-medium text-brand-ink hover:underline">
                Ver ligações <ArrowRight className="h-3 w-3" />
              </Link>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {alterado && (
            <Button variant="ghost" size="sm" onClick={() => setR(inicial)}>
              Desfazer
            </Button>
          )}
          <Button
            variant={alterado || !t.confirmada ? "primary" : "outline"}
            size="sm"
            disabled={!podeEditar || invalido || (!alterado && t.confirmada)}
            title={podeEditar ? undefined : "Seu perfil é só de leitura"}
            loading={salvar.isPending}
            onClick={() => salvar.mutate()}
          >
            <Check className="h-4 w-4" /> {alterado ? "Salvar" : t.confirmada ? "Salvo" : "Confirmar sugestão"}
          </Button>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[260px_1fr]">
        <fieldset>
          <legend className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-muted">Tipo</legend>
          <div className="flex flex-col gap-1" role="radiogroup">
            {(Object.keys(opcoes.tipos) as TipoTabulacao[]).map((tipo) => (
              <label
                key={tipo}
                className={cn(
                  "flex cursor-pointer items-start gap-2 rounded-xl border border-transparent px-2 py-1.5 text-sm transition hover:bg-raised",
                  r.tipo === tipo && "border-line bg-raised",
                )}
              >
                <input
                  type="radio"
                  name={`tipo-${t.id}`}
                  checked={r.tipo === tipo}
                  onChange={() => setR((x) => ({ ...x, tipo, ...(tipo !== "resultado" ? { categorias: [], subcategoria: null } : {}) }))}
                  className="mt-1 accent-[rgb(var(--brand))]"
                />
                <span>
                  <span className="block font-medium">{opcoes.tipos[tipo]}</span>
                  {r.tipo === tipo && <span className="block text-xs text-ink-muted">{TIPO_AJUDA[tipo]}</span>}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className={cn("flex flex-col gap-4 transition", r.tipo !== "resultado" && "pointer-events-none opacity-40")} aria-disabled={r.tipo !== "resultado"}>
          <div>
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-muted">
              Categorias da IA que confirmam esta tabulação
            </div>
            <div className="flex flex-wrap gap-2">
              {CATEGORIAS.filter((c) => c !== "INDETERMINADO").map((c) => {
                const on = r.categorias.includes(c);
                return (
                  <button
                    key={c}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleCat(c)}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-xl border px-3 py-1.5 text-sm transition active:scale-[.97]",
                      on ? "border-ink/40 bg-surface font-medium text-ink shadow-sm" : "border-line text-ink-muted hover:text-ink",
                    )}
                  >
                    <span className={cn("grid h-4 w-4 place-items-center rounded-[5px] border", on ? "border-transparent" : "border-line")} style={on ? { background: catColor(c) } : undefined}>
                      {on && <Check className="h-3 w-3 text-white" strokeWidth={3} />}
                    </span>
                    {opcoes.categorias[c]?.label ?? c}
                  </button>
                );
              })}
            </div>
            {invalido && <p className="mt-1.5 text-xs text-critical">Escolha ao menos uma categoria (ou mude o tipo).</p>}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-wide text-ink-muted">Subcategoria exigida (opcional)</span>
              <select
                value={r.subcategoria ?? ""}
                onChange={(e) => setR((x) => ({ ...x, subcategoria: e.target.value || null }))}
                disabled={!subs.length}
                className="h-9 w-full rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
              >
                <option value="">Qualquer subcategoria</option>
                {subs.map((s) => (
                  <option key={`${s.c}-${s.k}`} value={s.k}>
                    {s.v}
                  </option>
                ))}
              </select>
              <span className="mt-1 block text-xs text-ink-muted">Se escolher, subcategoria diferente vira divergência baixa.</span>
            </label>
            <label className="flex cursor-pointer items-start gap-2 self-start rounded-xl border border-line p-3 text-sm">
              <input
                type="checkbox"
                checked={r.nao_ligar}
                onChange={(e) => setR((x) => ({ ...x, nao_ligar: e.target.checked }))}
                className="mt-0.5 accent-[rgb(var(--brand))]"
              />
              <span>
                <span className="flex items-center gap-1.5 font-medium">
                  <PhoneOff className="h-3.5 w-3.5" /> Registra o pedido de não ligar
                </span>
                <span className="block text-xs text-ink-muted">É a tabulação que o operador deve usar quando o cliente pede para não receber mais ligações.</span>
              </span>
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}
