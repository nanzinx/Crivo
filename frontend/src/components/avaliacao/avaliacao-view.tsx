"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertOctagon,
  Ban,
  Check,
  ChevronDown,
  Flag,
  History,
  Keyboard,
  Loader2,
  LogOut,
  MessageSquare,
  Pause,
  Play,
  RotateCcw,
  RotateCw,
  Undo2,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { useAuth } from "@/components/auth-context";
import { Button, Card, CategoryBadge, Pill } from "@/components/ui/primitives";
import {
  api,
  audioUrl,
  type AvaliacaoCompleta,
  type Call,
  type Ciencia,
  type Desfecho,
  type EstadoItem,
  type Marca,
  type MarcaItem,
  type ScriptItem,
  type TipoMarca,
} from "@/lib/api";
import {
  CATEGORIAS,
  catColor,
  catLabel,
  cn,
  fmtClock,
  fmtDateTime,
  fmtDur,
} from "@/lib/utils";
import { ESTADOS, MARCA_COR, calcular, notaTone, secaoAplica } from "./calculo";

const DESFECHOS: { v: Desfecho; label: string; dica: string }[] = [
  { v: "venda", label: "Venda", dica: "Inclui a efetivação" },
  { v: "recusa", label: "Recusa", dica: "Inclui o tratamento da recusa" },
  { v: "outro", label: "Outro", dica: "Conversa sem venda nem recusa" },
  {
    v: "sem_conversa",
    label: "Sem conversa",
    dica: "Muda, caixa postal, não é o cliente",
  },
];
// sugestão de resultado da ligação quando a monitora escolhe o desfecho (só se ainda estiver vazio)
const CATEGORIA_SUGERIDA: Partial<Record<Desfecho, string>> = {
  venda: "EM_NEGOCIACAO",
  recusa: "SEM_INTERESSE",
};

type Campos = {
  desfecho: Desfecho | null;
  categoria: string | null;
  subcategoria: string | null;
  pediu_nao_ligar: boolean;
  observacao: string;
  feedback_fortes: string;
  feedback_melhorar: string;
};

const ehDigitacao = (el: EventTarget | null) =>
  el instanceof HTMLElement &&
  (el.tagName === "INPUT" ||
    el.tagName === "TEXTAREA" ||
    el.tagName === "SELECT" ||
    el.isContentEditable);

export function AvaliacaoView({
  call,
  inicial,
  somenteLeitura,
  aviso,
}: {
  call: Call;
  inicial: AvaliacaoCompleta;
  somenteLeitura: boolean;
  aviso?: ReactNode;
}) {
  const router = useRouter();
  const qc = useQueryClient();
  const [av, setAv] = useState(inicial);
  const script = av.script;
  const leitura = somenteLeitura || av.status !== "rascunho";

  // ------------------------------------------------------------ estado editável
  const [itens, setItens] = useState<Record<number, MarcaItem>>(() =>
    Object.fromEntries(inicial.itens.map((i) => [i.item_id, i])),
  );
  const [marcas, setMarcas] = useState<Marca[]>(inicial.marcas);
  const [campos, setCampos] = useState<Campos>({
    desfecho: inicial.desfecho,
    categoria: inicial.categoria,
    subcategoria: inicial.subcategoria,
    pediu_nao_ligar: inicial.pediu_nao_ligar,
    observacao: inicial.observacao ?? "",
    feedback_fortes: inicial.feedback_fortes ?? "",
    feedback_melhorar: inicial.feedback_melhorar ?? "",
  });
  const todosItens = useMemo(
    () =>
      script?.secoes.flatMap((s) => s.itens.map((i) => ({ ...i, secao: s }))) ??
      [],
    [script],
  );
  const aplicaveis = useMemo(
    () =>
      todosItens.filter((i) =>
        secaoAplica(i.secao.aplicabilidade, campos.desfecho),
      ),
    [todosItens, campos.desfecho],
  );
  const [sel, setSel] = useState<number | null>(
    () => todosItens[0]?.id ?? null,
  );
  const calc = useMemo(
    () => (script ? calcular(script, itens, campos.desfecho) : av.calculo),
    [script, itens, campos.desfecho, av.calculo],
  );

  // ------------------------------------------------------------ autosave
  const [sujo, setSujo] = useState(false);
  const [salvoEm, setSalvoEm] = useState<Date | null>(null);
  const payload = useCallback(
    () => ({
      ...campos,
      observacao: campos.observacao || null,
      feedback_fortes: campos.feedback_fortes || null,
      feedback_melhorar: campos.feedback_melhorar || null,
      itens: Object.values(itens),
      marcas,
    }),
    [campos, itens, marcas],
  );
  const salvar = useMutation({
    mutationFn: () => api.salvarAvaliacao(av.id, payload()),
    onSuccess: (r) => {
      setAv((a) => ({
        ...a,
        trava: r.trava,
        calculo: r.calculo,
        eventos: r.eventos,
      }));
      setSujo(false);
      setSalvoEm(new Date());
    },
    onError: (e) =>
      toast.error(`Não foi possível salvar: ${(e as Error).message}`),
  });
  const mudou = () => !leitura && setSujo(true);
  useEffect(() => {
    if (!sujo || leitura) return;
    const t = setTimeout(() => salvar.mutate(), 900);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sujo, campos, itens, marcas]);
  // renova a trava enquanto a tela está aberta (expira em 15 min sem atividade)
  useEffect(() => {
    if (leitura) return;
    const t = setInterval(
      () => api.salvarAvaliacao(av.id, {}).catch(() => undefined),
      5 * 60_000,
    );
    return () => clearInterval(t);
  }, [av.id, leitura]);
  // saiu da tela sem finalizar: salva o que falta e libera a ligação para outra monitora
  const ultimo = useRef({ sujo, payload, leitura });
  ultimo.current = { sujo, payload, leitura };
  useEffect(() => {
    const id = av.id;
    return () => {
      const u = ultimo.current;
      if (u.leitura) return;
      const opts = {
        keepalive: true,
        headers: { "Content-Type": "application/json" },
      };
      const salvarAntes = u.sujo
        ? fetch(`/api/v1/avaliacoes/${id}`, {
            ...opts,
            method: "PUT",
            body: JSON.stringify(u.payload()),
          })
        : Promise.resolve();
      salvarAntes.finally(() =>
        fetch(`/api/v1/avaliacoes/${id}/trava`, {
          ...opts,
          method: "DELETE",
        }).catch(() => undefined),
      );
    };
  }, [av.id]);

  // ------------------------------------------------------------ ações de item
  /** Clique no mesmo estado desmarca; pelo teclado (`alternar` falso) sempre marca. */
  const marcarItem = (
    id: number,
    estado: EstadoItem | null,
    alternar = true,
  ) => {
    if (leitura) return;
    setItens((p) => ({
      ...p,
      [id]: {
        item_id: id,
        estado: alternar && p[id]?.estado === estado ? null : estado,
        comentario: p[id]?.comentario ?? null,
      },
    }));
    mudou();
  };
  const comentar = (id: number, comentario: string) => {
    setItens((p) => ({
      ...p,
      [id]: { item_id: id, estado: p[id]?.estado ?? null, comentario },
    }));
    mudou();
  };
  const proximoPendente = (depoisDe: number | null) => {
    const lista = aplicaveis.map((i) => i.id);
    const idx = depoisDe == null ? -1 : lista.indexOf(depoisDe);
    const resto = [...lista.slice(idx + 1), ...lista.slice(0, idx + 1)];
    return resto.find((id) => !itens[id]?.estado && id !== depoisDe) ?? null;
  };

  // ------------------------------------------------------------ áudio
  const audio = useRef<HTMLAudioElement>(null);
  const [tempo, setTempo] = useState(0);
  const [duracao, setDuracao] = useState(call.duracao_segundos ?? 0);
  const [tocando, setTocando] = useState(false);
  const [vel, setVel] = useState(1);
  const temAudio = Boolean(call.tem_audio);
  const ir = (s: number) => {
    const t = Math.max(0, Math.min(s, duracao || s));
    if (audio.current && temAudio) audio.current.currentTime = t;
    setTempo(t);
  };
  const alternar = () => {
    const a = audio.current;
    if (!a || !temAudio) return;
    if (a.paused)
      a.play().catch((e) =>
        toast.error(`Não foi possível tocar: ${e.message}`),
      );
    else a.pause();
  };
  useEffect(() => {
    if (audio.current) audio.current.playbackRate = vel;
  }, [vel]);

  const novaMarca = (tipo: TipoMarca, itemId: number | null = sel) => {
    if (leitura) return;
    setMarcas((m) =>
      [
        ...m,
        {
          item_id: itemId,
          segundos: Math.round(tempo * 10) / 10,
          tipo,
          texto: null,
        },
      ].sort((a, b) => a.segundos - b.segundos),
    );
    mudou();
  };
  /** Toolbar "marcar agora": marca o item selecionado, registra o momento no áudio e vai para o próximo pendente. */
  const marcarAgora = (estado: Exclude<EstadoItem, "nao_se_aplica">) => {
    if (leitura || sel == null) return;
    setItens((p) => ({
      ...p,
      [sel]: { item_id: sel, estado, comentario: p[sel]?.comentario ?? null },
    }));
    novaMarca(estado, sel);
    if (estado === "acertou") {
      const prox = proximoPendente(sel);
      if (prox) setSel(prox);
    }
  };

  // ------------------------------------------------------------ atalhos
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (ehDigitacao(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      const lista = aplicaveis.map((i) => i.id);
      const pos = sel == null ? -1 : lista.indexOf(sel);
      if (e.key === " ") {
        e.preventDefault();
        alternar();
      } else if (e.key === "ArrowLeft") ir(tempo - 5);
      else if (e.key === "ArrowRight") ir(tempo + 5);
      else if (e.key === "j" && lista.length)
        setSel(lista[Math.min(pos + 1, lista.length - 1)]);
      else if (e.key === "k" && lista.length)
        setSel(lista[Math.max(pos - 1, 0)]);
      else if (["1", "2", "3", "4"].includes(e.key) && sel != null) {
        const estado = ESTADOS[Number(e.key) - 1].v;
        marcarItem(sel, estado, false);
        // acertou / não se aplica: segue para o próximo item; erro e divergência ficam para comentar
        if (
          (estado === "acertou" || estado === "nao_se_aplica") &&
          pos < lista.length - 1
        )
          setSel(lista[pos + 1]);
      } else if (e.key === "m")
        novaMarca(
          (sel != null &&
          itens[sel]?.estado &&
          itens[sel]?.estado !== "nao_se_aplica"
            ? itens[sel]!.estado
            : "nota") as TipoMarca,
        );
      else return;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // ------------------------------------------------------------ finalizar / não avaliável / reabrir / sair
  const depois = (r: AvaliacaoCompleta, msg: string) => {
    setAv(r);
    qc.invalidateQueries();
    toast.success(msg);
  };
  const finalizar = useMutation({
    mutationFn: async () => {
      if (sujo) await api.salvarAvaliacao(av.id, payload());
      return api.finalizarAvaliacao(av.id);
    },
    onSuccess: (r) => {
      setSujo(false);
      depois(
        r,
        r.nota != null
          ? `Avaliação concluída · nota ${r.nota.toLocaleString("pt-BR")}`
          : "Avaliação concluída",
      );
    },
    onError: (e) => toast.error((e as Error).message, { duration: 8000 }),
  });
  const [motivo, setMotivo] = useState<{
    tipo: "nao_avaliavel" | "reabrir";
    texto: string;
  } | null>(null);
  const naoAvaliavel = useMutation({
    mutationFn: (m: string) => api.naoAvaliavel(av.id, m),
    onSuccess: (r) => {
      setMotivo(null);
      depois(r, "Marcada como não avaliável");
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const reabrir = useMutation({
    mutationFn: (m: string) => api.reabrirAvaliacao(av.id, m),
    onSuccess: (r) => {
      setMotivo(null);
      depois(r, "Avaliação reaberta");
      router.refresh();
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const proxima = useMutation({
    mutationFn: () => api.fila({ page: 1 }),
    onSuccess: (f) => {
      const p = f.itens.find(
        (c) => c.id !== call.id && (!c.rascunho?.trava || c.rascunho.minha),
      );
      if (p) router.push(`/monitoria/avaliar/${p.id}`);
      else {
        toast("A fila está vazia 🎉");
        router.push("/monitoria");
      }
    },
  });

  const { data: tax } = useQuery({
    queryKey: ["taxonomy"],
    queryFn: api.taxonomy,
    staleTime: Infinity,
  });
  const subs =
    campos.categoria && tax?.[campos.categoria]
      ? Object.entries(tax[campos.categoria].subs)
      : [];
  const setCampo = <K extends keyof Campos>(k: K, v: Campos[K]) => {
    setCampos((c) => ({ ...c, [k]: v }));
    mudou();
  };
  const marcasDoItem = (id: number) => marcas.filter((m) => m.item_id === id);
  const itemPorId = useMemo(
    () => new Map(todosItens.map((i) => [i.id, i])),
    [todosItens],
  );
  const numero = useMemo(
    () => new Map(todosItens.map((i, n) => [i.id, n + 1])),
    [todosItens],
  );
  const problemas = [
    !campos.desfecho && "Escolha o desfecho",
    !campos.categoria && "Escolha o resultado da ligação",
    calc &&
      calc.pendentes.length > 0 &&
      `${calc.pendentes.length} item(ns) sem marcação`,
    calc &&
      calc.sem_comentario.length > 0 &&
      `${calc.sem_comentario.length} erro(s)/divergência(s) sem comentário`,
  ].filter(Boolean) as string[];

  if (!script) {
    return (
      <Card title="Sem script">
        Esta avaliação foi um registro rápido, sem o script.
      </Card>
    );
  }

  return (
    <div className="space-y-4 pb-24">
      {aviso}
      {av.status !== "rascunho" && (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-line bg-surface p-3 text-sm">
          <Pill tone={av.status === "finalizada" ? "good" : "warn"}>
            {av.status === "finalizada" ? "Finalizada" : "Não avaliável"}
          </Pill>
          <span className="text-ink-2">
            por {av.monitora_nome} · {fmtDateTime(av.finalizada_em)}
          </span>
          {av.nao_avaliavel_motivo && (
            <span className="text-ink-2">— {av.nao_avaliavel_motivo}</span>
          )}
          {!somenteLeitura && (
            <Button
              size="sm"
              variant="outline"
              className="ml-auto"
              onClick={() => setMotivo({ tipo: "reabrir", texto: "" })}
            >
              <Undo2 className="h-3.5 w-3.5" /> Reabrir
            </Button>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {/* ------------------------------------------------ coluna do áudio */}
        <div className="space-y-4 lg:sticky lg:top-4 lg:self-start">
          <section className="card p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="truncate text-lg font-semibold tracking-tight">
                  {call.operador_nome ?? "Operador não identificado"}
                </h1>
                <p className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-ink-muted">
                  <span className="num">{fmtDateTime(call.data_ligacao)}</span>·
                  <span className="num">{fmtDur(call.duracao_segundos)}</span>
                  {call.id_ligacao && <>· #{call.id_ligacao}</>}
                </p>
              </div>
              <Nota calc={calc} />
            </div>
            <div className="mt-3 rounded-xl bg-raised px-3 py-2 text-xs">
              <span className="text-ink-muted">Operador tabulou: </span>
              <b className="font-medium">{call.tabulacao_operador || "—"}</b>
            </div>

            {/* player */}
            <div className="mt-4">
              {temAudio ? (
                <audio
                  ref={audio}
                  src={audioUrl(call.id)}
                  preload="metadata"
                  onLoadedMetadata={(e) =>
                    Number.isFinite(e.currentTarget.duration) &&
                    setDuracao(e.currentTarget.duration)
                  }
                  onTimeUpdate={(e) => setTempo(e.currentTarget.currentTime)}
                  onPlay={() => setTocando(true)}
                  onPause={() => setTocando(false)}
                />
              ) : (
                <p className="mb-2 rounded-lg bg-warn/15 px-2.5 py-1.5 text-[11px] text-ink-2">
                  Sem gravação disponível: arraste o cursor para marcar os
                  momentos manualmente.
                </p>
              )}
              <Timeline
                tempo={tempo}
                duracao={duracao}
                marcas={marcas}
                selecionado={sel}
                onSeek={ir}
                onMarca={(m) => {
                  ir(m.segundos);
                  if (m.item_id) setSel(m.item_id);
                }}
                titulo={(m) =>
                  m.item_id
                    ? `${numero.get(m.item_id)}. ${itemPorId.get(m.item_id)?.texto ?? ""}`
                    : (m.texto ?? "Nota")
                }
              />
              <div className="mt-3 flex items-center gap-2">
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => ir(tempo - 5)}
                  aria-label="Voltar 5 segundos"
                >
                  <RotateCcw className="h-4 w-4" />
                </Button>
                <Button
                  size="icon"
                  variant="primary"
                  onClick={alternar}
                  disabled={!temAudio}
                  aria-label={tocando ? "Pausar" : "Tocar"}
                  className="h-10 w-10 rounded-full"
                >
                  {tocando ? (
                    <Pause className="h-4 w-4" />
                  ) : (
                    <Play className="ml-0.5 h-4 w-4" />
                  )}
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => ir(tempo + 5)}
                  aria-label="Avançar 5 segundos"
                >
                  <RotateCw className="h-4 w-4" />
                </Button>
                <span className="num text-xs text-ink-2">
                  {fmtClock(tempo)} / {fmtClock(duracao)}
                </span>
                <div
                  className="ml-auto flex rounded-lg bg-raised p-0.5 text-[11px]"
                  role="radiogroup"
                  aria-label="Velocidade"
                >
                  {[1, 1.25, 1.5, 2].map((v) => (
                    <button
                      key={v}
                      role="radio"
                      aria-checked={vel === v}
                      onClick={() => setVel(v)}
                      className={cn(
                        "rounded-md px-1.5 py-0.5 text-ink-muted",
                        vel === v &&
                          "bg-surface font-medium text-ink shadow-sm",
                      )}
                    >
                      {v.toLocaleString("pt-BR")}×
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* marcar agora */}
            {!leitura && (
              <div className="mt-4 rounded-xl border border-dashed border-line p-3">
                <p className="mb-2 text-[11px] text-ink-muted">
                  Marcar agora ({fmtClock(tempo)}) no item{" "}
                  <b className="font-medium text-ink">
                    {sel != null ? `${numero.get(sel)}` : "—"}
                  </b>
                </p>
                <div className="grid grid-cols-4 gap-1.5">
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-good/40 text-good"
                    disabled={sel == null}
                    onClick={() => marcarAgora("acertou")}
                  >
                    <Check className="h-3.5 w-3.5" /> Acertou
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-critical/40 text-critical"
                    disabled={sel == null}
                    onClick={() => marcarAgora("errou")}
                  >
                    <X className="h-3.5 w-3.5" /> Errou
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-warn/60"
                    disabled={sel == null}
                    onClick={() => marcarAgora("divergencia")}
                  >
                    ≈ Diverg.
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => novaMarca("nota", sel)}
                  >
                    <Flag className="h-3.5 w-3.5" /> Nota
                  </Button>
                </div>
              </div>
            )}

            {marcas.length > 0 && (
              <ul
                className="mt-3 flex flex-wrap gap-1.5"
                aria-label="Marcadores"
              >
                {marcas.map((m, i) => (
                  <li
                    key={i}
                    className="group flex items-center gap-1 rounded-full border border-line bg-surface pl-1.5 pr-1 text-[11px]"
                  >
                    <span
                      className={cn("h-2 w-2 rounded-full", MARCA_COR[m.tipo])}
                    />
                    <button
                      className="num py-0.5 hover:underline"
                      onClick={() => (
                        ir(m.segundos),
                        m.item_id && setSel(m.item_id)
                      )}
                    >
                      {fmtClock(m.segundos)}
                    </button>
                    <span className="max-w-[9rem] truncate text-ink-muted">
                      {m.item_id
                        ? `item ${numero.get(m.item_id)}`
                        : (m.texto ?? "nota")}
                    </span>
                    {!leitura && (
                      <button
                        onClick={() => {
                          setMarcas((ms) => ms.filter((_, j) => j !== i));
                          mudou();
                        }}
                        className="rounded-full p-0.5 text-ink-muted hover:bg-raised hover:text-ink"
                        aria-label="Remover marcador"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <Atalhos />
        </div>

        {/* ------------------------------------------------ coluna do script */}
        <div className="space-y-4">
          <section className="card p-4">
            <h2 className="card-title mb-2">Desfecho da ligação</h2>
            <div
              className="grid grid-cols-2 gap-1.5 sm:grid-cols-4"
              role="radiogroup"
              aria-label="Desfecho"
            >
              {DESFECHOS.map((d) => (
                <button
                  key={d.v}
                  role="radio"
                  aria-checked={campos.desfecho === d.v}
                  disabled={leitura}
                  onClick={() => {
                    setCampos((c) => ({
                      ...c,
                      desfecho: d.v,
                      categoria: c.categoria ?? CATEGORIA_SUGERIDA[d.v] ?? null,
                    }));
                    mudou();
                  }}
                  className={cn(
                    "rounded-xl border px-3 py-2 text-left transition disabled:cursor-default",
                    campos.desfecho === d.v
                      ? "border-ink/40 bg-surface shadow-sm"
                      : "border-line text-ink-2 hover:border-ink/20",
                  )}
                >
                  <div className="text-sm font-medium">{d.label}</div>
                  <div className="text-[11px] text-ink-muted">{d.dica}</div>
                </button>
              ))}
            </div>
          </section>

          {script.secoes.map((s) => {
            const aplica = secaoAplica(s.aplicabilidade, campos.desfecho);
            return (
              <section
                key={s.id}
                className={cn("card overflow-hidden", !aplica && "opacity-60")}
              >
                <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
                  <h3 className="text-sm font-semibold">{s.titulo}</h3>
                  {s.aplicabilidade !== "sempre" && (
                    <Pill tone={aplica ? "brand" : "neutral"}>
                      {aplica
                        ? s.aplicabilidade_label
                        : `${s.aplicabilidade_label}: fora deste desfecho`}
                    </Pill>
                  )}
                </header>
                {aplica ? (
                  <ol className="divide-y divide-line">
                    {s.itens.map((it) => (
                      <ItemLinha
                        key={it.id}
                        n={numero.get(it.id) ?? 0}
                        item={it}
                        marca={itens[it.id]}
                        marcas={marcasDoItem(it.id)}
                        ativo={sel === it.id}
                        leitura={leitura}
                        semComentario={!!calc?.sem_comentario.includes(it.id)}
                        onSelecionar={() => setSel(it.id)}
                        onEstado={(e) => marcarItem(it.id, e)}
                        onComentario={(t) => comentar(it.id, t)}
                        onIr={ir}
                      />
                    ))}
                  </ol>
                ) : (
                  <p className="px-4 py-3 text-xs text-ink-muted">
                    {campos.desfecho
                      ? "Não entra na nota deste desfecho."
                      : "Escolha o desfecho para saber se este bloco entra na nota."}
                  </p>
                )}
              </section>
            );
          })}

          {/* resultado e feedback */}
          <section className="card space-y-4 p-4">
            <div>
              <h2 className="card-title mb-2">Resultado da ligação</h2>
              <div
                className="flex flex-wrap gap-1.5"
                role="radiogroup"
                aria-label="Resultado da ligação"
              >
                {CATEGORIAS.map((k) => (
                  <button
                    key={k}
                    role="radio"
                    aria-checked={campos.categoria === k}
                    disabled={leitura}
                    onClick={() => {
                      setCampos((c) => ({
                        ...c,
                        categoria: k,
                        subcategoria: null,
                      }));
                      mudou();
                    }}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition disabled:cursor-default",
                      campos.categoria === k
                        ? "border-ink/40 bg-surface font-medium text-ink shadow-sm"
                        : "border-line text-ink-muted hover:text-ink",
                    )}
                  >
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ background: catColor(k) }}
                    />
                    {catLabel(k)}
                  </button>
                ))}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                {subs.length > 0 && (
                  <select
                    value={campos.subcategoria ?? ""}
                    disabled={leitura}
                    onChange={(e) =>
                      setCampo("subcategoria", e.target.value || null)
                    }
                    className="h-9 min-w-0 flex-1 rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
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
                  <input
                    type="checkbox"
                    disabled={leitura}
                    checked={campos.pediu_nao_ligar}
                    onChange={(e) =>
                      setCampo("pediu_nao_ligar", e.target.checked)
                    }
                    className="accent-brand"
                  />
                  Pediu para não ligar mais (LGPD)
                </label>
              </div>
            </div>
            <Texto
              label="Observação geral"
              value={campos.observacao}
              leitura={leitura}
              onChange={(v) => setCampo("observacao", v)}
              placeholder="O que chamou atenção na ligação"
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Texto
                label="Pontos fortes (feedback)"
                value={campos.feedback_fortes}
                leitura={leitura}
                onChange={(v) => setCampo("feedback_fortes", v)}
                placeholder="O que o operador fez bem"
              />
              <Texto
                label="A melhorar (feedback)"
                value={campos.feedback_melhorar}
                leitura={leitura}
                onChange={(v) => setCampo("feedback_melhorar", v)}
                placeholder="O que treinar com o operador"
              />
            </div>
            <p className="text-[11px] text-ink-muted">
              O feedback chega ao operador pelo supervisor.
            </p>
          </section>

          {av.status === "finalizada" && <CienciaCard avaliacaoId={av.id} inicial={inicial.ciencia ?? null} />}
          {av.eventos.length > 0 && <Auditoria eventos={av.eventos} />}
        </div>
      </div>

      {/* ------------------------------------------------ barra de ações (portal: o wrapper animado da página tem transform) */}
      <NoBody>
        <div className="fixed inset-x-0 bottom-[calc(56px+env(safe-area-inset-bottom))] z-30 border-t border-line bg-surface/95 px-4 py-2.5 backdrop-blur lg:bottom-0 lg:left-60">
          <AnimatePresence>
            {motivo && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="mx-auto mb-2 flex max-w-5xl gap-2">
                  <input
                    autoFocus
                    value={motivo.texto}
                    onChange={(e) =>
                      setMotivo({ ...motivo, texto: e.target.value })
                    }
                    placeholder={
                      motivo.tipo === "reabrir"
                        ? "Por que reabrir? (fica na auditoria)"
                        : "Por que não dá para avaliar? (áudio cortado, sem som...)"
                    }
                    className="h-9 min-w-0 flex-1 rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-brand"
                    onKeyDown={(e) => e.key === "Escape" && setMotivo(null)}
                  />
                  <Button
                    size="md"
                    variant="primary"
                    disabled={!motivo.texto.trim()}
                    loading={naoAvaliavel.isPending || reabrir.isPending}
                    onClick={() =>
                      motivo.tipo === "reabrir"
                        ? reabrir.mutate(motivo.texto)
                        : naoAvaliavel.mutate(motivo.texto)
                    }
                  >
                    Confirmar
                  </Button>
                  <Button
                    size="md"
                    variant="ghost"
                    onClick={() => setMotivo(null)}
                  >
                    Cancelar
                  </Button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2">
            <span className="flex min-w-0 items-center gap-1.5 text-[11px] text-ink-muted">
              {leitura ? (
                "Somente leitura"
              ) : salvar.isPending ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin" /> Salvando…
                </>
              ) : sujo ? (
                "Alterações não salvas"
              ) : salvoEm ? (
                `Salvo às ${salvoEm.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`
              ) : (
                "Rascunho salvo automaticamente"
              )}
            </span>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              {!leitura ? (
                <>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => router.push("/monitoria")}
                    title="Salva e libera a ligação"
                  >
                    <LogOut className="h-3.5 w-3.5" /> Sair
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      setMotivo({ tipo: "nao_avaliavel", texto: "" })
                    }
                  >
                    <Ban className="h-3.5 w-3.5" /> Não avaliável
                  </Button>
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => finalizar.mutate()}
                    loading={finalizar.isPending}
                    title={
                      problemas.length
                        ? problemas.join(" · ")
                        : "Concluir a avaliação"
                    }
                    className={cn(problemas.length > 0 && "opacity-70")}
                  >
                    <Check className="h-3.5 w-3.5" /> Finalizar
                    {problemas.length > 0 && (
                      <span className="rounded-full bg-surface/20 px-1.5 text-[10px]">
                        {problemas.length}
                      </span>
                    )}
                  </Button>
                </>
              ) : (
                !somenteLeitura && (
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => proxima.mutate()}
                    loading={proxima.isPending}
                  >
                    Próxima da fila
                  </Button>
                )
              )}
            </div>
          </div>
        </div>
      </NoBody>
    </div>
  );
}

// ---------------------------------------------------------------- peças

function NoBody({ children }: { children: ReactNode }) {
  const [montado, setMontado] = useState(false);
  useEffect(() => setMontado(true), []);
  return montado ? createPortal(children, document.body) : null;
}

function Nota({ calc }: { calc: ReturnType<typeof calcular> | null }) {
  return (
    <div className="shrink-0 text-right">
      <div
        className={cn(
          "num text-3xl font-semibold leading-none tracking-tight",
          notaTone(calc?.nota),
        )}
        aria-live="polite"
      >
        {calc?.nota != null ? calc.nota.toLocaleString("pt-BR") : "–"}
      </div>
      <div className="mt-1 text-[11px] text-ink-muted">nota</div>
      {calc?.falha_critica && (
        <Pill tone="critical" className="mt-1">
          <AlertOctagon className="h-3 w-3" /> falha crítica
        </Pill>
      )}
    </div>
  );
}

function Timeline({
  tempo,
  duracao,
  marcas,
  selecionado,
  onSeek,
  onMarca,
  titulo,
}: {
  tempo: number;
  duracao: number;
  marcas: Marca[];
  selecionado: number | null;
  onSeek: (s: number) => void;
  onMarca: (m: Marca) => void;
  titulo: (m: Marca) => string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const pct = (s: number) =>
    duracao > 0 ? Math.min(100, (100 * s) / duracao) : 0;
  const seekPelo = (clientX: number) => {
    const r = ref.current?.getBoundingClientRect();
    if (!r || !duracao) return;
    onSeek(((clientX - r.left) / r.width) * duracao);
  };
  return (
    <div
      ref={ref}
      role="slider"
      tabIndex={0}
      aria-label="Posição na gravação"
      aria-valuemin={0}
      aria-valuemax={Math.round(duracao)}
      aria-valuenow={Math.round(tempo)}
      aria-valuetext={fmtClock(tempo)}
      className="relative h-10 cursor-pointer touch-none select-none rounded-xl bg-raised"
      onPointerDown={(e) => {
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
        seekPelo(e.clientX);
      }}
      onPointerMove={(e) => e.buttons === 1 && seekPelo(e.clientX)}
    >
      <div
        className="absolute inset-y-0 left-0 rounded-xl bg-brand/15"
        style={{ width: `${pct(tempo)}%` }}
      />
      <div
        className="absolute inset-y-1 w-0.5 rounded-full bg-brand"
        style={{ left: `${pct(tempo)}%` }}
      />
      {marcas.map((m, i) => (
        <button
          key={i}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => onMarca(m)}
          title={`${fmtClock(m.segundos)} · ${titulo(m)}`}
          aria-label={`Marcador em ${fmtClock(m.segundos)}: ${titulo(m)}`}
          className={cn(
            "absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface shadow transition hover:scale-125",
            MARCA_COR[m.tipo],
            m.item_id != null &&
              m.item_id === selecionado &&
              "ring-2 ring-ink/40",
          )}
          style={{ left: `${pct(m.segundos)}%` }}
        />
      ))}
    </div>
  );
}

function ItemLinha({
  n,
  item,
  marca,
  marcas,
  ativo,
  leitura,
  semComentario,
  onSelecionar,
  onEstado,
  onComentario,
  onIr,
}: {
  n: number;
  item: ScriptItem;
  marca?: MarcaItem;
  marcas: Marca[];
  ativo: boolean;
  leitura: boolean;
  semComentario: boolean;
  onSelecionar: () => void;
  onEstado: (e: EstadoItem) => void;
  onComentario: (t: string) => void;
  onIr: (s: number) => void;
}) {
  const estado = marca?.estado ?? null;
  const pedeComentario = estado === "errou" || estado === "divergencia";
  const [abrirComentario, setAbrirComentario] = useState(false);
  const mostrarComentario =
    pedeComentario || abrirComentario || !!marca?.comentario;
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (ativo)
      ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [ativo]);
  return (
    <li
      ref={ref}
      onClick={onSelecionar}
      className={cn(
        "relative px-4 py-3 transition",
        ativo ? "bg-brand-soft/50" : "hover:bg-raised/40",
      )}
      aria-current={ativo || undefined}
    >
      {ativo && (
        <span
          className="absolute inset-y-2 left-0 w-1 rounded-r-full bg-brand"
          aria-hidden
        />
      )}
      <div className="flex gap-3">
        <span className="num mt-0.5 w-5 shrink-0 text-right text-xs text-ink-muted">
          {n}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm leading-relaxed text-ink">
            {item.texto}
            {item.critico && (
              <Pill tone="critical" className="ml-1.5 align-middle">
                crítico
              </Pill>
            )}
            {item.peso !== 1 && (
              <span className="ml-1.5 align-middle text-[11px] text-ink-muted">
                peso {item.peso.toLocaleString("pt-BR")}
              </span>
            )}
          </p>
          {item.orientacao && (
            <p className="mt-0.5 text-xs text-ink-muted">{item.orientacao}</p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {ESTADOS.map((e) => (
              <button
                key={e.v}
                type="button"
                disabled={leitura}
                aria-pressed={estado === e.v}
                onClick={(ev) => {
                  ev.stopPropagation();
                  onSelecionar();
                  onEstado(e.v);
                }}
                title={`${e.label} (tecla ${e.tecla})`}
                className={cn(
                  "inline-flex h-7 items-center gap-1 rounded-lg border border-line px-2 text-xs text-ink-muted transition disabled:cursor-default",
                  estado === e.v ? e.ativo : !leitura && e.cls,
                  leitura && estado !== e.v && "opacity-40",
                )}
              >
                <span aria-hidden>{e.curto}</span> {e.label}
              </button>
            ))}
            {marcas.map((m, i) => (
              <button
                key={i}
                onClick={(ev) => {
                  ev.stopPropagation();
                  onIr(m.segundos);
                }}
                className="num inline-flex items-center gap-1 rounded-full bg-raised px-2 py-0.5 text-[11px] text-ink-2 hover:text-ink"
                title="Ir para este momento da gravação"
              >
                <span
                  className={cn("h-1.5 w-1.5 rounded-full", MARCA_COR[m.tipo])}
                />{" "}
                {fmtClock(m.segundos)}
              </button>
            ))}
            {!leitura && !mostrarComentario && (
              <button
                onClick={(ev) => {
                  ev.stopPropagation();
                  setAbrirComentario(true);
                }}
                className="inline-flex items-center gap-1 text-[11px] text-ink-muted hover:text-ink"
              >
                <MessageSquare className="h-3 w-3" /> comentar
              </button>
            )}
          </div>

          {mostrarComentario && (
            <textarea
              value={marca?.comentario ?? ""}
              readOnly={leitura}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => onComentario(e.target.value)}
              rows={2}
              placeholder={
                pedeComentario
                  ? "Obrigatório: o que o operador falou ou deixou de falar?"
                  : "Comentário (opcional)"
              }
              aria-label={`Comentário do item ${n}`}
              className={cn(
                "mt-2 w-full resize-none rounded-xl border bg-surface p-2 text-sm outline-none focus:border-brand",
                semComentario ? "border-warn" : "border-line",
              )}
            />
          )}
        </div>
      </div>
    </li>
  );
}

function Texto({
  label,
  value,
  onChange,
  leitura,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  leitura: boolean;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium text-ink-muted">
        {label}
      </span>
      <textarea
        value={value}
        readOnly={leitura}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        placeholder={leitura ? "—" : placeholder}
        className="w-full resize-none rounded-xl border border-line bg-surface p-2.5 text-sm outline-none focus:border-brand"
      />
    </label>
  );
}

function CienciaCard({ avaliacaoId, inicial }: { avaliacaoId: number; inicial: Ciencia | null }) {
  const { usuario, estado } = useAuth();
  const pode = !estado?.auth_ativo || usuario?.papel === "supervisor" || usuario?.papel === "admin";
  const [ci, setCi] = useState(inicial);
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState(inicial?.devolutiva ?? "");
  const qc = useQueryClient();
  const salvar = useMutation({
    mutationFn: () => api.darCiencia(avaliacaoId, texto),
    onSuccess: (r) => {
      setCi(r);
      setEditando(false);
      qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("sup-") });
      toast.success("Ciência registrada");
    },
    onError: (e) => toast.error((e as Error).message),
  });
  if (!ci && !pode) {
    return (
      <section className="card p-4 text-sm text-ink-muted">
        <h2 className="card-title mb-1 text-ink">Ciência do supervisor</h2>O supervisor da equipe ainda não registrou a devolutiva ao operador.
      </section>
    );
  }
  return (
    <section className={cn("card p-4", !ci && "border-warn/50")}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="card-title">Ciência do supervisor</h2>
        {ci ? (
          <Pill tone="good">
            <Check className="h-3 w-3" /> {ci.por} · {fmtDateTime(ci.em)}
          </Pill>
        ) : (
          <Pill tone="warn">pendente</Pill>
        )}
      </div>
      {ci && !editando ? (
        <div className="space-y-2 text-sm">
          <p className="text-ink-2">{ci.devolutiva || "Ciência sem devolutiva escrita."}</p>
          {pode && (
            <Button size="sm" variant="ghost" onClick={() => setEditando(true)}>
              Atualizar devolutiva
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={3}
            placeholder="Como foi a devolutiva ao operador? (ex.: conversado no 1:1, combinou treinar a abertura)"
            aria-label="Devolutiva ao operador"
            className="w-full resize-none rounded-xl border border-line bg-surface p-2.5 text-sm outline-none focus:border-brand"
          />
          <div className="flex justify-end gap-2">
            {editando && (
              <Button size="sm" variant="ghost" onClick={() => setEditando(false)}>
                Cancelar
              </Button>
            )}
            <Button size="sm" variant="primary" onClick={() => salvar.mutate()} loading={salvar.isPending}>
              <Check className="h-3.5 w-3.5" /> Registrar ciência
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}

const ACOES: Record<string, string> = {
  iniciada: "Iniciou a avaliação",
  finalizada: "Finalizou",
  reaberta: "Reabriu",
  nao_avaliavel: "Marcou como não avaliável",
  trava_liberada: "Liberou a avaliação de outra pessoa",
};

function Auditoria({ eventos }: { eventos: AvaliacaoCompleta["eventos"] }) {
  const [aberto, setAberto] = useState(false);
  return (
    <section className="card p-4">
      <button
        onClick={() => setAberto((v) => !v)}
        className="flex w-full items-center justify-between text-sm font-semibold"
        aria-expanded={aberto}
      >
        <span className="flex items-center gap-1.5">
          <History className="h-4 w-4 text-ink-muted" /> Histórico (
          {eventos.length})
        </span>
        <ChevronDown
          className={cn("h-4 w-4 transition-transform", aberto && "rotate-180")}
        />
      </button>
      {aberto && (
        <ol className="mt-3 space-y-2 text-xs">
          {eventos.map((e, i) => {
            const d = e.detalhe as {
              motivo?: string;
              nota?: number | null;
              antes?: { nota?: number | null; categoria?: string | null };
            } | null;
            return (
              <li key={i} className="flex gap-2">
                <span className="num shrink-0 text-ink-muted">
                  {fmtDateTime(e.em)}
                </span>
                <span>
                  <b className="font-medium">{e.usuario}</b> ·{" "}
                  {ACOES[e.acao] ?? e.acao}
                  {d?.nota != null &&
                    ` (nota ${d.nota.toLocaleString("pt-BR")})`}
                  {d?.motivo && (
                    <span className="text-ink-2"> — “{d.motivo}”</span>
                  )}
                  {d?.antes && (
                    <span className="text-ink-muted">
                      {" "}
                      · antes: nota{" "}
                      {d.antes.nota != null
                        ? d.antes.nota.toLocaleString("pt-BR")
                        : "–"}
                      ,{" "}
                      <CategoryBadge
                        code={d.antes.categoria}
                        className="text-[11px]"
                      />
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function Atalhos() {
  return (
    <details className="card hidden p-4 text-xs text-ink-2 lg:block">
      <summary className="flex cursor-pointer items-center gap-1.5 font-medium text-ink">
        <Keyboard className="h-4 w-4 text-ink-muted" /> Atalhos de teclado
      </summary>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        {[
          ["espaço", "tocar / pausar"],
          ["← →", "voltar / avançar 5 s"],
          ["j / k", "próximo / anterior item"],
          [
            "1 2 3 4",
            "acertou · errou · divergência · não se aplica (1 e 4 já vão para o próximo)",
          ],
          ["m", "marcador no momento atual"],
        ].map(([k, v]) => (
          <div key={k} className="contents">
            <dt>
              <kbd className="rounded border border-line bg-raised px-1.5 font-mono text-[10px]">
                {k}
              </kbd>
            </dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
