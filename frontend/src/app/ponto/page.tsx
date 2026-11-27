"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Clock, Coffee, Download, FileUp, Settings2, Timer, UserCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth-context";
import { Button, Card, Empty, Pill, Select, Skeleton } from "@/components/ui/primitives";
import Link from "next/link";
import { api, operadorUrl, pontoExportUrl, type PontoConfig, type PontoImportado, type PontoLinha } from "@/lib/api";
import { cn, fmtDateTime, fmtDay, fmtInt } from "@/lib/utils";

type Aba = "completo" | "entrada" | "config";

const hhmm = (s: number | null | undefined, comSeg = false) => {
  if (s == null) return "–";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}${comSeg ? `:${String(r).padStart(2, "0")}` : ""}`;
};
const hora = (iso: string | null) => (iso ? iso.slice(11, 16) : "–");

export default function PontoPage() {
  const { usuario, estado } = useAuth();
  const podeImportar = !estado?.auth_ativo || usuario?.papel === "monitora" || usuario?.papel === "admin";
  const [aba, setAba] = useState<Aba>("completo");
  const [data, setData] = useState<string>("");
  const [grupo, setGrupo] = useState("");
  const { data: datas } = useQuery({ queryKey: ["ponto-datas"], queryFn: api.pontoDatas });

  // dia fechado = o mais recente com pausas; dia em andamento = o mais recente
  useEffect(() => {
    if (!datas?.length) return;
    const alvo = aba === "entrada" ? datas[0] : datas.find((d) => d.tem_pausas) ?? datas[0];
    setData(alvo.data);
  }, [datas, aba]);

  const modo = aba === "entrada" ? "entrada" : "completo";
  const { data: rel, isLoading } = useQuery({
    queryKey: ["ponto-rel", data, modo, grupo],
    queryFn: () => api.pontoRelatorio({ data, modo, grupo: grupo || undefined }),
    enabled: !!data && aba !== "config",
  });
  const grupos = [...new Set((rel?.linhas ?? []).map((l) => l.grupo).filter(Boolean))] as string[];

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs text-ink-muted">Entradas, saídas, almoço e pausas da operação</p>
          <h1 className="text-2xl font-semibold tracking-tight">Controle de ponto</h1>
        </div>
        <div className="flex rounded-xl bg-raised p-1 text-xs" role="tablist">
          {(
            [
              ["completo", "Dia fechado"],
              ["entrada", "Entradas de hoje"],
              ...(podeImportar ? ([["config", "Configuração"]] as const) : []),
            ] as const
          ).map(([k, l]) => (
            <button
              key={k}
              role="tab"
              aria-selected={aba === k}
              onClick={() => setAba(k)}
              className={cn("rounded-lg px-3 py-1.5 font-medium text-ink-muted", aba === k && "bg-surface text-ink shadow-sm")}
            >
              {l}
            </button>
          ))}
        </div>
      </header>

      {podeImportar && <Importar />}

      {aba === "config" ? (
        <Configuracao />
      ) : !datas ? (
        <Skeleton className="h-64" />
      ) : !datas.length ? (
        <Card>
          <Empty icon={<Clock className="h-5 w-5" />} title="Nenhum ponto importado ainda">
            Exporte do Argus os relatórios de entrada/saída e de pausas em CSV e arraste aqui em cima.
          </Empty>
        </Card>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Select aria-label="Dia" value={data} onChange={(e) => setData(e.target.value)} className="w-48">
              {datas.map((d) => (
                <option key={d.data} value={d.data}>
                  {fmtDay(d.data)}/{d.data.slice(0, 4)}
                  {aba === "completo" && !d.tem_pausas ? " (sem pausas)" : ""}
                </option>
              ))}
            </Select>
            {grupos.length > 1 && (
              <Select aria-label="Equipe" value={grupo} onChange={(e) => setGrupo(e.target.value)} className="w-52">
                <option value="">Todas as equipes</option>
                {grupos.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </Select>
            )}
            {data && (
              <a href={pontoExportUrl({ data, modo, grupo: grupo || undefined })} className="ml-auto">
                <Button variant="outline" size="sm">
                  <Download className="h-3.5 w-3.5" /> Exportar CSV
                </Button>
              </a>
            )}
          </div>

          <section className={cn("grid grid-cols-2 gap-3", modo === "completo" ? "lg:grid-cols-5" : "lg:grid-cols-2")}>
            <Kpi icon={<UserCheck className="h-4 w-4" />} label="Presentes" valor={rel ? fmtInt(rel.resumo.presentes) : undefined} />
            <Kpi
              icon={<AlertTriangle className="h-4 w-4" />}
              label="Atrasos"
              valor={rel ? fmtInt(rel.resumo.atrasos) : undefined}
              cls={rel?.resumo.atrasos ? "text-critical" : undefined}
            />
            {modo === "completo" && (
              <>
                <Kpi icon={<Coffee className="h-4 w-4" />} label="Almoço médio" valor={rel ? hhmm(rel.resumo.almoco_medio_seg) : undefined} />
                <Kpi
                  icon={<Coffee className="h-4 w-4" />}
                  label="Almoço acima de 1h"
                  valor={rel ? fmtInt(rel.resumo.almoco_acima_1h ?? 0) : undefined}
                  cls={rel?.resumo.almoco_acima_1h ? "text-warn" : undefined}
                />
                <Kpi icon={<Timer className="h-4 w-4" />} label="TMP médio" valor={rel ? hhmm(rel.resumo.tmp_medio_seg, true) : undefined} />
              </>
            )}
          </section>

          <Card
            title={modo === "completo" ? `Entradas, saídas e pausas · ${data ? fmtDay(data) : ""}` : `Entradas · ${data ? fmtDay(data) : ""}`}
            subtitle={
              modo === "completo"
                ? "TMP = tempo total nas pausas que contam (almoço à parte) · QTP = quantidade dessas pausas"
                : "Dia em andamento: só a entrada e o atraso"
            }
          >
            {isLoading || !rel ? <Skeleton className="h-64" /> : <Tabela linhas={rel.linhas} completo={modo === "completo"} />}
          </Card>
        </>
      )}
    </div>
  );
}

function Kpi({ icon, label, valor, cls }: { icon: React.ReactNode; label: string; valor?: string; cls?: string }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-1.5 text-xs text-ink-muted">
        {icon} {label}
      </div>
      {valor == null ? <Skeleton className="mt-2 h-7 w-16" /> : <div className={cn("num mt-1 text-2xl font-semibold tracking-tight", cls)}>{valor}</div>}
    </div>
  );
}

function Tabela({ linhas, completo }: { linhas: PontoLinha[]; completo: boolean }) {
  if (!linhas.length) return <Empty title="Ninguém neste filtro" />;
  return (
    <div className="-mx-4 overflow-x-auto sm:mx-0">
      <table className={cn("w-full text-sm", completo ? "min-w-[920px]" : "min-w-[480px]")}>
        <thead>
          <tr className="border-b border-line text-left text-[11px] uppercase tracking-wide text-ink-muted">
            <th className="px-4 py-2 font-medium sm:px-0">Colaborador</th>
            <th className="py-2 text-center font-medium">Entrada</th>
            {completo && (
              <>
                <th className="py-2 text-center font-medium">Saída</th>
                <th className="py-2 text-center font-medium">Jornada</th>
                <th className="py-2 text-center font-medium">Almoço</th>
                <th className="py-2 text-center font-medium">Tempo almoço</th>
                <th className="py-2 text-center font-medium">TMP</th>
                <th className="py-2 text-center font-medium">QTP</th>
              </>
            )}
            <th className="py-2 pr-4 font-medium sm:pr-0">Observação</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {linhas.map((l) => {
            const almocoLongo = (l.almoco_seg ?? 0) > 3600;
            return (
              <tr key={l.operador} className={cn(l.atraso_min > 0 && "bg-critical/[.07]")}>
                <td className="px-4 py-2 sm:px-0">
                  <Link href={operadorUrl(l.operador)} className={cn("font-medium hover:underline", l.atraso_min > 0 && "text-critical")}>
                    {l.operador}
                  </Link>
                  {l.grupo && <div className="text-[11px] text-ink-muted">{l.grupo}</div>}
                </td>
                <td className="num py-2 text-center">{hhmm(l.entrada_seg)}</td>
                {completo && (
                  <>
                    <td className="num py-2 text-center">{hhmm(l.saida_seg)}</td>
                    <td className="num py-2 text-center">{hhmm(l.jornada_seg)}</td>
                    <td className="num py-2 text-center text-ink-2">
                      {l.almoco_inicio ? `${hora(l.almoco_inicio)}–${hora(l.almoco_fim)}` : "–"}
                    </td>
                    <td className={cn("num py-2 text-center", almocoLongo && "font-semibold text-warn")}>{hhmm(l.almoco_seg, true)}</td>
                    <td className="num py-2 text-center">{hhmm(l.tmp_seg, true)}</td>
                    <td className="num py-2 text-center">{l.qtp ?? "–"}</td>
                  </>
                )}
                <td className="py-2 pr-4 sm:pr-0">
                  <div className="flex flex-wrap gap-1">
                    {l.atraso_min > 0 && (
                      <Pill tone="critical">
                        <AlertTriangle className="h-3 w-3" /> Atraso de {l.atraso_min} min
                      </Pill>
                    )}
                    {completo && almocoLongo && (
                      <Pill tone="warn">
                        <Coffee className="h-3 w-3" /> almoço acima de 1h
                      </Pill>
                    )}
                    {l.entrada_seg == null && <Pill>sem entrada</Pill>}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Importar() {
  const qc = useQueryClient();
  const ref = useRef<HTMLInputElement>(null);
  const [arrastando, setArrastando] = useState(false);
  const [resultado, setResultado] = useState<PontoImportado[] | null>(null);
  const { data: hist } = useQuery({ queryKey: ["ponto-imp"], queryFn: api.pontoImportacoes });
  const importar = useMutation({
    mutationFn: (fs: File[]) => api.pontoImportar(fs),
    onSuccess: (r) => {
      setResultado(r.arquivos);
      qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("ponto") });
      const erros = r.arquivos.filter((a) => a.erro).length;
      if (erros) toast.warning(`${erros} arquivo(s) não importados`);
      else toast.success(`${r.arquivos.length} arquivo(s) importados`);
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const argus = useMutation({
    mutationFn: () => api.pontoDoArgus(new Date().toLocaleDateString("sv-SE")),
    onSuccess: (r) => {
      qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("ponto") });
      toast.success(`Ponto de hoje atualizado pelo Argus: ${fmtInt(r.ponto.linhas)} linhas${r.pausas ? ` e ${fmtInt(r.pausas.linhas)} pausas` : ""}`);
    },
    onError: (e) => toast.error((e as Error).message, { duration: 10_000 }),
  });
  const enviar = (fs: FileList | null) => fs && fs.length && importar.mutate(Array.from(fs));
  const ultima = hist?.[0];
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setArrastando(true);
      }}
      onDragLeave={() => setArrastando(false)}
      onDrop={(e) => {
        e.preventDefault();
        setArrastando(false);
        enviar(e.dataTransfer.files);
      }}
      className={cn(
        "flex flex-wrap items-center gap-3 rounded-2xl border-2 border-dashed p-4 transition",
        arrastando ? "border-brand bg-brand-soft/50" : "border-line",
      )}
    >
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand-ink">
        <FileUp className="h-5 w-5" />
      </span>
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-medium">Importar relatórios do Argus</p>
        <p className="text-xs text-ink-muted">
          Com o token do Argus configurado, o ponto chega sozinho a cada 30 min. Sem ele, arraste os CSVs de entrada/saída e de pausas; se o dia já existir, substitui.
          {ultima && ` Última: ${ultima.arquivo} (${fmtDateTime(ultima.importado_em)}).`}
        </p>
        {resultado && (
          <ul className="mt-2 space-y-0.5 text-xs">
            {resultado.map((a) => (
              <li key={a.arquivo} className={a.erro ? "text-critical" : "text-ink-2"}>
                <b className="font-medium">{a.arquivo}</b>:{" "}
                {a.erro ??
                  `${a.tipo === "ponto" ? "entrada/saída" : "pausas"} de ${a.data ? fmtDay(a.data) : "?"} · ${fmtInt(a.linhas)} linhas${a.substituiu ? " (substituiu a importação anterior)" : ""}`}
              </li>
            ))}
          </ul>
        )}
      </div>
      <Button variant="outline" size="sm" onClick={() => argus.mutate()} loading={argus.isPending} title="Busca pela API do Argus o ponto e as pausas de hoje (precisa do ARGUS_TOKEN)">
        Buscar no Argus
      </Button>
      <input ref={ref} type="file" accept=".csv,text/csv" multiple hidden onChange={(e) => (enviar(e.target.files), (e.target.value = ""))} />
      <Button variant="primary" size="sm" onClick={() => ref.current?.click()} loading={importar.isPending}>
        Escolher arquivos
      </Button>
    </div>
  );
}

function Configuracao() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["ponto-config"], queryFn: api.pontoConfig });
  const [cfg, setCfg] = useState<PontoConfig | null>(null);
  useEffect(() => {
    if (data) setCfg(data);
  }, [data]);
  const salvar = useMutation({
    mutationFn: () =>
      api.salvarPontoConfig({
        grupos: cfg!.grupos.map(({ grupo, incluir, entrada_prevista, tolerancia_min }) => ({ grupo, incluir, entrada_prevista, tolerancia_min })),
        pausas: cfg!.pausas,
        almoco: cfg!.almoco,
        ignorar: cfg!.ignorar,
      }),
    onSuccess: (r) => {
      setCfg(r);
      qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("ponto") });
      toast.success("Configuração salva: os relatórios já usam os novos valores");
    },
    onError: (e) => toast.error((e as Error).message),
  });
  if (!cfg) return <Skeleton className="h-96" />;
  const campo = "h-8 rounded-lg border border-line bg-surface px-2 text-sm outline-none focus:border-brand";
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-5">
        <Card title="Grupos do Argus" subtitle="Grupo novo entra sozinho na importação" className="lg:col-span-3">
          <div className="-mx-4 overflow-x-auto sm:mx-0">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-[11px] uppercase tracking-wide text-ink-muted">
                  <th className="px-4 py-2 font-medium sm:px-0">Grupo</th>
                  <th className="py-2 font-medium">No relatório</th>
                  <th className="py-2 font-medium">Entrada prevista</th>
                  <th className="py-2 pr-4 font-medium sm:pr-0">Tolerância</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {cfg.grupos.map((g, i) => {
                  const set = (patch: Partial<typeof g>) => setCfg({ ...cfg, grupos: cfg.grupos.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
                  return (
                    <tr key={g.grupo}>
                      <td className="px-4 py-2 sm:px-0">
                        <div className="font-medium">{g.grupo}</div>
                        <div className="text-[11px] text-ink-muted">{g.operadores} operador(es) no ponto</div>
                      </td>
                      <td className="py-2">
                        <label className="flex items-center gap-1.5 text-xs">
                          <input type="checkbox" checked={g.incluir} onChange={(e) => set({ incluir: e.target.checked })} className="accent-brand" />
                          {g.incluir ? "Sim" : "Não"}
                        </label>
                      </td>
                      <td className="py-2">
                        <input
                          value={g.entrada_prevista}
                          onChange={(e) => set({ entrada_prevista: e.target.value })}
                          placeholder="10:00 ou 08:30;14:00"
                          aria-label={`Entrada prevista de ${g.grupo}`}
                          className={cn(campo, "w-36")}
                        />
                      </td>
                      <td className="py-2 pr-4 sm:pr-0">
                        <input
                          type="number"
                          min={0}
                          max={240}
                          value={g.tolerancia_min}
                          onChange={(e) => set({ tolerancia_min: Number(e.target.value) })}
                          aria-label={`Tolerância de ${g.grupo}`}
                          className={cn(campo, "w-16")}
                        />{" "}
                        <span className="text-xs text-ink-muted">min</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-ink-muted">
            Vários turnos: separe com ponto e vírgula. O atraso compara com o turno mais próximo e só conta acima da tolerância.
          </p>
        </Card>
        <Card title="Pausas" subtitle="Quais entram no TMP/QTP" className="lg:col-span-2">
          <ul className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            {cfg.pausas.map((p, i) => (
              <li key={p.descricao}>
                <label className="flex items-center gap-2 rounded-lg px-2 py-1 text-sm hover:bg-raised">
                  <input
                    type="checkbox"
                    checked={p.conta}
                    onChange={(e) => setCfg({ ...cfg, pausas: cfg.pausas.map((x, j) => (j === i ? { ...x, conta: e.target.checked } : x)) })}
                    className="accent-brand"
                  />
                  {p.descricao}
                </label>
              </li>
            ))}
          </ul>
          <div className="mt-4 grid gap-3 border-t border-line pt-4 text-sm">
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-ink-muted">Nome da pausa de almoço</span>
              <input value={cfg.almoco} onChange={(e) => setCfg({ ...cfg, almoco: e.target.value })} className={cn(campo, "w-full")} />
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-ink-muted">Ignorar operadores com o texto</span>
              <input value={cfg.ignorar} onChange={(e) => setCfg({ ...cfg, ignorar: e.target.value })} className={cn(campo, "w-full")} />
            </label>
          </div>
        </Card>
      </div>
      <div className="flex justify-end">
        <Button variant="primary" onClick={() => salvar.mutate()} loading={salvar.isPending}>
          <Settings2 className="h-4 w-4" /> Salvar configuração
        </Button>
      </div>
    </div>
  );
}
