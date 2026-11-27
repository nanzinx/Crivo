"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, FilePlus2, Pencil, Plus, Rocket, Save, ScrollText, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth-context";
import { Button, Card, Empty, Pill, Skeleton } from "@/components/ui/primitives";
import { api, type Aplicabilidade, type ScriptIn, type ScriptVersao } from "@/lib/api";
import { cn, fmtDateTime } from "@/lib/utils";

const APL: Record<Aplicabilidade, string> = { sempre: "Sempre", venda: "Só se houve venda", recusa: "Só se houve recusa" };
const STATUS: Record<string, { label: string; tone: "good" | "brand" | "neutral" }> = {
  ativa: { label: "em uso", tone: "good" },
  rascunho: { label: "rascunho", tone: "brand" },
  arquivada: { label: "arquivada", tone: "neutral" },
};

export default function ScriptPage() {
  const { admin } = useAuth();
  const qc = useQueryClient();
  const { data: versoes } = useQuery({ queryKey: ["script-versoes"], queryFn: api.scriptVersoes });
  const [vid, setVid] = useState<number | null>(null);
  const ativa = versoes?.find((v) => v.status === "ativa");
  const atual = vid ?? ativa?.id ?? versoes?.[0]?.id ?? null;
  const { data: v, isLoading } = useQuery({
    queryKey: ["script-versao", atual],
    queryFn: () => api.scriptVersao(atual!),
    enabled: atual != null,
  });
  const recarregar = () => qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("script") });

  const novo = useMutation({
    mutationFn: api.novoRascunhoScript,
    onSuccess: (r) => {
      setVid(r.id);
      recarregar();
    },
    onError: (e) => toast.error((e as Error).message),
  });

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs text-ink-muted">Monitoria de qualidade</p>
          <h1 className="text-2xl font-semibold tracking-tight">Script de vendas</h1>
        </div>
        {admin && !versoes?.some((x) => x.status === "rascunho") && (
          <Button variant="soft" onClick={() => novo.mutate()} loading={novo.isPending}>
            <FilePlus2 className="h-4 w-4" /> Nova versão
          </Button>
        )}
      </header>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="min-w-0">
          {isLoading || !v ? (
            <Skeleton className="h-96" />
          ) : v.status === "rascunho" && admin ? (
            <Editor v={v} onSalvo={recarregar} onPublicado={() => (setVid(null), recarregar())} onDescartado={() => (setVid(null), recarregar())} />
          ) : (
            <Leitura v={v} />
          )}
        </div>
        <Card title="Versões" subtitle="A avaliação guarda a versão usada" className="h-fit">
          {!versoes ? (
            <Skeleton className="h-24" />
          ) : (
            <ul className="space-y-1">
              {versoes.map((x) => (
                <li key={x.id}>
                  <button
                    onClick={() => setVid(x.id)}
                    className={cn("w-full rounded-xl px-3 py-2 text-left text-sm transition hover:bg-raised", x.id === atual && "bg-raised")}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">Versão {x.numero}</span>
                      <Pill tone={STATUS[x.status].tone}>{STATUS[x.status].label}</Pill>
                    </div>
                    <div className="mt-0.5 text-[11px] text-ink-muted">
                      {x.avaliacoes} avaliação(ões) · {fmtDateTime(x.publicada_em ?? x.criado_em)}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function Leitura({ v }: { v: ScriptVersao }) {
  let n = 0;
  return (
    <article className="card p-5 sm:p-7">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-2 border-b border-line pb-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{v.nome}</h2>
          <p className="mt-0.5 text-xs text-ink-muted">
            Versão {v.numero} · divergência vale {(v.valor_divergencia * 100).toLocaleString("pt-BR")}% de um acerto · trechos entre colchetes são variáveis
          </p>
        </div>
        <Pill tone={STATUS[v.status].tone}>{STATUS[v.status].label}</Pill>
      </div>
      {!v.secoes.length && <Empty icon={<ScrollText className="h-5 w-5" />} title="Script vazio" />}
      <ol className="space-y-7">
        {v.secoes.map((s, si) => (
          <li key={s.id}>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h3 className="text-base font-semibold">
                <span className="text-ink-muted">{si + 1}.</span> {s.titulo}
              </h3>
              {s.aplicabilidade !== "sempre" && <Pill tone="brand">{s.aplicabilidade_label}</Pill>}
            </div>
            {s.orientacao && <p className="mb-2 text-sm text-ink-muted">{s.orientacao}</p>}
            <ul className="space-y-2 border-l-2 border-line pl-4">
              {s.itens.map((it) => {
                n += 1;
                return (
                  <li key={it.id} className="text-[15px] leading-relaxed">
                    <span className="num mr-2 text-xs text-ink-muted">{n}</span>
                    {it.texto}
                    {it.critico && (
                      <Pill tone="critical" className="ml-2 align-middle">
                        crítico
                      </Pill>
                    )}
                    {it.peso !== 1 && <span className="ml-2 text-xs text-ink-muted">peso {it.peso.toLocaleString("pt-BR")}</span>}
                    {it.orientacao && <p className="ml-6 text-sm text-ink-muted">{it.orientacao}</p>}
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ol>
    </article>
  );
}

type Rasc = ScriptIn;

function paraRascunho(v: ScriptVersao): Rasc {
  return {
    nome: v.nome,
    valor_divergencia: v.valor_divergencia,
    secoes: v.secoes.map((s) => ({
      titulo: s.titulo,
      aplicabilidade: s.aplicabilidade,
      orientacao: s.orientacao,
      itens: s.itens.map((i) => ({ texto: i.texto, orientacao: i.orientacao, peso: i.peso, critico: i.critico })),
    })),
  };
}

function mover<T>(lista: T[], i: number, d: number): T[] {
  const j = i + d;
  if (j < 0 || j >= lista.length) return lista;
  const c = [...lista];
  [c[i], c[j]] = [c[j], c[i]];
  return c;
}

function Editor({ v, onSalvo, onPublicado, onDescartado }: { v: ScriptVersao; onSalvo: () => void; onPublicado: () => void; onDescartado: () => void }) {
  const [r, setR] = useState<Rasc>(() => paraRascunho(v));
  const [sujo, setSujo] = useState(false);
  useEffect(() => {
    setR(paraRascunho(v));
    setSujo(false);
  }, [v]);
  const mudar = (f: (x: Rasc) => Rasc) => {
    setR(f);
    setSujo(true);
  };
  const setSecao = (si: number, patch: Partial<Rasc["secoes"][number]>) =>
    mudar((x) => ({ ...x, secoes: x.secoes.map((s, i) => (i === si ? { ...s, ...patch } : s)) }));
  const setItem = (si: number, ii: number, patch: Partial<Rasc["secoes"][number]["itens"][number]>) =>
    setSecao(si, { itens: r.secoes[si].itens.map((it, j) => (j === ii ? { ...it, ...patch } : it)) });

  const salvar = useMutation({
    mutationFn: () => api.salvarScript(v.id, r),
    onSuccess: () => {
      setSujo(false);
      toast.success("Rascunho salvo");
      onSalvo();
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const publicar = useMutation({
    mutationFn: async () => {
      if (sujo) await api.salvarScript(v.id, r);
      return api.publicarScript(v.id);
    },
    onSuccess: (x) => {
      toast.success(`Versão ${x.numero} publicada: as próximas avaliações usam este script`);
      onPublicado();
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const descartar = useMutation({
    mutationFn: () => api.descartarScript(v.id),
    onSuccess: () => {
      toast("Rascunho descartado");
      onDescartado();
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const campo = "w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-brand";
  return (
    <div className="space-y-4">
      <div className="card space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Pencil className="h-4 w-4 text-ink-muted" />
            <h2 className="font-semibold">Editando a versão {v.numero} (rascunho)</h2>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => descartar.mutate()} loading={descartar.isPending}>
              <Trash2 className="h-3.5 w-3.5" /> Descartar
            </Button>
            <Button size="sm" variant="outline" onClick={() => salvar.mutate()} loading={salvar.isPending} disabled={!sujo}>
              <Save className="h-3.5 w-3.5" /> Salvar
            </Button>
            <Button size="sm" variant="primary" onClick={() => publicar.mutate()} loading={publicar.isPending}>
              <Rocket className="h-3.5 w-3.5" /> Publicar
            </Button>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-[1fr_200px]">
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-ink-muted">Nome</span>
            <input value={r.nome} onChange={(e) => mudar((x) => ({ ...x, nome: e.target.value }))} className={campo} />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-ink-muted">Divergência vale (% de um acerto)</span>
            <input
              type="number"
              min={0}
              max={100}
              step={5}
              value={Math.round(r.valor_divergencia * 100)}
              onChange={(e) => mudar((x) => ({ ...x, valor_divergencia: Math.max(0, Math.min(100, Number(e.target.value))) / 100 }))}
              className={campo}
            />
          </label>
        </div>
        <p className="text-xs text-ink-muted">
          Publicar troca o script das próximas avaliações. As avaliações já feitas continuam com a versão delas.
        </p>
      </div>

      {r.secoes.map((s, si) => (
        <section key={si} className="card space-y-3 p-4">
          <div className="flex flex-wrap items-end gap-2">
            <label className="min-w-0 flex-1">
              <span className="mb-1 block text-[11px] font-medium text-ink-muted">Bloco {si + 1}</span>
              <input value={s.titulo} onChange={(e) => setSecao(si, { titulo: e.target.value })} className={cn(campo, "font-medium")} />
            </label>
            <label>
              <span className="mb-1 block text-[11px] font-medium text-ink-muted">Entra na nota</span>
              <select value={s.aplicabilidade} onChange={(e) => setSecao(si, { aplicabilidade: e.target.value as Aplicabilidade })} className={campo}>
                {Object.entries(APL).map(([k, l]) => (
                  <option key={k} value={k}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex">
              <Button size="icon" variant="ghost" aria-label="Subir bloco" onClick={() => mudar((x) => ({ ...x, secoes: mover(x.secoes, si, -1) }))}>
                <ArrowUp className="h-4 w-4" />
              </Button>
              <Button size="icon" variant="ghost" aria-label="Descer bloco" onClick={() => mudar((x) => ({ ...x, secoes: mover(x.secoes, si, 1) }))}>
                <ArrowDown className="h-4 w-4" />
              </Button>
              <Button size="icon" variant="ghost" aria-label="Remover bloco" onClick={() => mudar((x) => ({ ...x, secoes: x.secoes.filter((_, i) => i !== si) }))}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <ol className="space-y-2">
            {s.itens.map((it, ii) => (
              <li key={ii} className="rounded-xl border border-line p-3">
                <div className="flex gap-2">
                  <textarea
                    value={it.texto}
                    onChange={(e) => setItem(si, ii, { texto: e.target.value })}
                    rows={2}
                    aria-label={`Texto do item ${ii + 1}`}
                    className={cn(campo, "resize-y")}
                  />
                  <div className="flex flex-col">
                    <Button size="icon" variant="ghost" aria-label="Subir item" onClick={() => setSecao(si, { itens: mover(s.itens, ii, -1) })}>
                      <ArrowUp className="h-3.5 w-3.5" />
                    </Button>
                    <Button size="icon" variant="ghost" aria-label="Descer item" onClick={() => setSecao(si, { itens: mover(s.itens, ii, 1) })}>
                      <ArrowDown className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
                  <input
                    value={it.orientacao ?? ""}
                    onChange={(e) => setItem(si, ii, { orientacao: e.target.value || null })}
                    placeholder="Orientação para a monitora (opcional)"
                    className={cn(campo, "h-8 min-w-0 flex-1 py-1 text-xs")}
                  />
                  <label className="flex items-center gap-1.5">
                    Peso
                    <input
                      type="number"
                      min={0.5}
                      max={10}
                      step={0.5}
                      value={it.peso}
                      onChange={(e) => setItem(si, ii, { peso: Math.max(0.5, Number(e.target.value) || 1) })}
                      className={cn(campo, "h-8 w-16 py-1 text-xs")}
                    />
                  </label>
                  <label className="flex items-center gap-1.5">
                    <input type="checkbox" checked={it.critico} onChange={(e) => setItem(si, ii, { critico: e.target.checked })} className="accent-brand" />
                    Crítico
                  </label>
                  <button
                    onClick={() => setSecao(si, { itens: s.itens.filter((_, j) => j !== ii) })}
                    className="inline-flex items-center gap-1 text-ink-muted hover:text-critical"
                  >
                    <X className="h-3.5 w-3.5" /> remover
                  </button>
                </div>
              </li>
            ))}
          </ol>
          <Button size="sm" variant="ghost" onClick={() => setSecao(si, { itens: [...s.itens, { texto: "", peso: 1, critico: false }] })}>
            <Plus className="h-3.5 w-3.5" /> Item
          </Button>
        </section>
      ))}
      <Button variant="outline" onClick={() => mudar((x) => ({ ...x, secoes: [...x.secoes, { titulo: "Novo bloco", aplicabilidade: "sempre", itens: [] }] }))}>
        <Plus className="h-4 w-4" /> Bloco
      </Button>
    </div>
  );
}
