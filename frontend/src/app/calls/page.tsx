"use client";
import { useCallback, useEffect, useState, useRef } from "react";
import AudioDrawer from "@/components/AudioDrawer";
import DateFilter from "@/components/DateFilter";
import GlobalBottomPlayer from "@/components/GlobalBottomPlayer";
import { API, COLORS, fmtDate, fmtDur, get, qs, exportCsvUrl } from "@/lib/api";
import {
  Play,
  Pause,
  Volume2,
  FileText,
  Search,
  Filter,
  Download,
  RotateCcw,
  PhoneOff,
  AlertTriangle,
} from "lucide-react";

const PAGE_SIZE = 50;

export default function Calls() {
  const [f, setF] = useState<any>({
    data_inicio: "",
    data_fim: "",
    categoria: "",
    subcategoria: "",
    tronco: "",
    tipo_agente: "",
    tipo_discagem: "",
    desligado_por: "",
    divergencia: "",
    operador: "",
    q: "",
    telefone: "",
  });
  const [ready, setReady] = useState(false);
  const [tax, setTax] = useState<any>({});
  const [filterOpts, setFilterOpts] = useState<any>({
    operadores: [],
    troncos: [],
    tipos_agente: ["COMERCIAL", "DIGITAL"],
    tipos_discagem: ["ATIVO", "URA"],
    desligado_por: ["CLIENTE", "OPERADOR"],
    categorias: [],
  });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<any>({ items: [], total: 0 });
  const [sel, setSel] = useState<number | null>(null);

  // Player de Áudio
  const [playingCall, setPlayingCall] = useState<any>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeed] = useState(1.0);
  const globalAudioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    const a = new Audio();
    globalAudioRef.current = a;

    a.addEventListener("timeupdate", () => {
      setCurrentTime(a.currentTime);
      if (a.duration) setDuration(a.duration);
    });
    a.addEventListener("play", () => setIsPlaying(true));
    a.addEventListener("pause", () => setIsPlaying(false));
    a.addEventListener("ended", () => {
      handlePlayNext();
    });

    return () => {
      a.pause();
      a.src = "";
    };
  }, []);

  useEffect(() => {
    const p = Object.fromEntries(new URLSearchParams(window.location.search));
    setF((o: any) => ({ ...o, ...p }));
    setReady(true);
    get<any>("/api/v1/taxonomy").then(setTax).catch(() => {});
    get<any>("/api/v1/analyst/filters-options").then(setFilterOpts).catch(() => {});
  }, []);

  const load = useCallback(() => {
    const params: Record<string, any> = {
      ...f,
      divergencia: f.divergencia === "" ? undefined : f.divergencia === "true",
      page,
      page_size: PAGE_SIZE,
    };
    get<any>("/api/v1/calls", params)
      .then(setData)
      .catch(() => {});
  }, [f, page]);

  useEffect(() => {
    if (ready) load();
  }, [ready, load]);

  const setFilter = (k: string, v: string) => {
    setPage(1);
    setF((o: any) => ({
      ...o,
      [k]: v,
      ...(k === "categoria" ? { subcategoria: "" } : {}),
    }));
  };

  const handleResetFilters = () => {
    setPage(1);
    setF({
      data_inicio: "",
      data_fim: "",
      categoria: "",
      subcategoria: "",
      tronco: "",
      tipo_agente: "",
      tipo_discagem: "",
      desligado_por: "",
      divergencia: "",
      operador: "",
      q: "",
      telefone: "",
    });
  };

  const playCall = (item: any) => {
    const a = globalAudioRef.current;
    if (!a) return;

    if (playingCall?.id === item.id) {
      if (a.paused) a.play().catch(() => {});
      else a.pause();
      return;
    }

    setPlayingCall(item);
    a.src = `${API}/api/v1/calls/${item.id}/audio`;
    a.playbackRate = speed;
    a.play().catch(() => {});
  };

  const togglePlay = () => {
    const a = globalAudioRef.current;
    if (!a) return;
    if (!playingCall && data.items.length > 0) {
      playCall(data.items[0]);
      return;
    }
    if (a.paused) a.play().catch(() => {});
    else a.pause();
  };

  const seekRelative = (sec: number) => {
    const a = globalAudioRef.current;
    if (!a) return;
    a.currentTime = Math.max(0, Math.min(a.duration || 0, a.currentTime + sec));
  };

  const handleSeek = (pos: number) => {
    const a = globalAudioRef.current;
    if (!a) return;
    a.currentTime = pos;
  };

  const handleSpeedChange = (s: number) => {
    setSpeed(s);
    if (globalAudioRef.current) globalAudioRef.current.playbackRate = s;
  };

  const handlePlayNext = () => {
    if (!playingCall || data.items.length === 0) return;
    const curIdx = data.items.findIndex((c: any) => c.id === playingCall.id);
    if (curIdx >= 0 && curIdx < data.items.length - 1) {
      playCall(data.items[curIdx + 1]);
    }
  };

  const handlePlayPrev = () => {
    if (!playingCall || data.items.length === 0) return;
    const curIdx = data.items.findIndex((c: any) => c.id === playingCall.id);
    if (curIdx > 0) {
      playCall(data.items[curIdx - 1]);
    }
  };

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            <span>Explorador de Ligações</span>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-mono">
              {data.total} registradas
            </span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Filtros multi-dimensionais, validação de tabulação humana vs IA, e sinalização SIP de desligamento.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <a
            href={exportCsvUrl(f)}
            download
            className="px-3 py-2 rounded-xl text-xs font-semibold bg-emerald-600/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-600/30 transition flex items-center gap-1.5"
          >
            <Download size={14} />
            <span>Exportar CSV</span>
          </a>
        </div>
      </div>

      {/* Painel de Filtros Avançados */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-xl space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
          <div className="flex items-center gap-2 text-white font-semibold text-xs">
            <Filter size={14} className="text-indigo-400" />
            <span>Filtros do Analista de Dados</span>
          </div>

          <button
            onClick={handleResetFilters}
            className="text-xs text-slate-400 hover:text-rose-400 flex items-center gap-1 transition px-2 py-1 rounded bg-slate-800/60"
          >
            <RotateCcw size={12} />
            <span>Limpar</span>
          </button>
        </div>

        {/* Linha 1 */}
        <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-6 gap-2.5 text-xs">
          <div className="md:col-span-2">
            <DateFilter
              ini={f.data_inicio}
              fim={f.data_fim}
              onChange={(i, fm) => {
                setPage(1);
                setF((o: any) => ({ ...o, data_inicio: i, data_fim: fm }));
              }}
            />
          </div>

          <div className="md:col-span-2 relative">
            <Search size={14} className="absolute left-3 top-3 text-slate-500" />
            <input
              type="text"
              placeholder="Buscar cliente, tel, operador, transcrição..."
              value={f.q || ""}
              onChange={(e) => setFilter("q", e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div>
            <select
              value={f.tronco || ""}
              onChange={(e) => setFilter("tronco", e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500"
            >
              <option value="">Tronco: Todos</option>
              <option value="4NET">4NET - BENCONSIG</option>
              <option value="VENDITORE">VENDITORE - URA</option>
              {filterOpts.troncos?.map((t: any) => (
                <option key={t.nome} value={t.nome}>
                  {t.nome} ({t.total})
                </option>
              ))}
            </select>
          </div>

          <div>
            <select
              value={f.operador || ""}
              onChange={(e) => setFilter("operador", e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500"
            >
              <option value="">Operador: Todos</option>
              {filterOpts.operadores?.map((op: any) => (
                <option key={op.nome} value={op.nome}>
                  {op.nome} ({op.total})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Linha 2 */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5 text-xs pt-1">
          <div>
            <select
              value={f.tipo_agente || ""}
              onChange={(e) => setFilter("tipo_agente", e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none"
            >
              <option value="">Equipe: Comercial / Digital</option>
              <option value="COMERCIAL">COMERCIAL (Equipe Comercial)</option>
              <option value="DIGITAL">DIGITAL (Equipe Digital)</option>
            </select>
          </div>

          <div>
            <select
              value={f.tipo_discagem || ""}
              onChange={(e) => setFilter("tipo_discagem", e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none"
            >
              <option value="">Discagem: Ativo / URA</option>
              <option value="ATIVO">ATIVO</option>
              <option value="URA">URA</option>
            </select>
          </div>

          <div>
            <select
              value={f.desligado_por || ""}
              onChange={(e) => setFilter("desligado_por", e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none"
            >
              <option value="">Desligado Por: Todos</option>
              <option value="CLIENTE">CLIENTE (BYE recebido)</option>
              <option value="OPERADOR">OPERADOR (BYE enviado)</option>
            </select>
          </div>

          <div>
            <select
              value={f.divergencia || ""}
              onChange={(e) => setFilter("divergencia", e.target.value)}
              className={`w-full border rounded-xl px-3 py-2 text-white focus:outline-none ${
                f.divergencia === "true"
                  ? "bg-amber-950/60 border-amber-500/60 text-amber-200"
                  : "bg-slate-950 border-slate-800"
              }`}
            >
              <option value="">Auditoria: Todas</option>
              <option value="true">⚠️ Com Divergência de Tabulação</option>
              <option value="false">✓ Sem Divergência</option>
            </select>
          </div>

          <div>
            <select
              value={f.categoria || ""}
              onChange={(e) => setFilter("categoria", e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none"
            >
              <option value="">Categoria IA: Todas</option>
              <option value="EM_NEGOCIACAO">Em Negociação</option>
              <option value="NAO_E_O_CLIENTE">Não é o Cliente</option>
              <option value="SEM_INTERESSE">Cliente Não tem Interesse</option>
              <option value="LIGACAO_MUDA">Ligação Muda</option>
              <option value="CAIXA_POSTAL">Caixa Postal</option>
            </select>
          </div>
        </div>
      </div>

      {/* Tabela de Resultados */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-xl overflow-hidden text-xs">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-slate-400 uppercase tracking-wider text-[11px] bg-slate-950/40">
              <th className="py-3 px-2 text-center w-12">Áudio</th>
              <th className="py-3 px-3">Data / Hora</th>
              <th className="py-3 px-3">Tronco / Agente</th>
              <th className="py-3 px-3">Operador</th>
              <th className="py-3 px-3">Cliente / Telefone</th>
              <th className="py-3 px-3 text-center">Desligado Por</th>
              <th className="py-3 px-3">Tabulação Operador vs IA</th>
              <th className="py-3 px-2 text-right">Duração</th>
              <th className="py-3 px-3 text-center">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-sans">
            {data.items.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-12 text-center text-slate-500">
                  Nenhuma ligação encontrada com os filtros selecionados.
                </td>
              </tr>
            ) : (
              data.items.map((call: any) => {
                const isCurrentPlaying = playingCall?.id === call.id && isPlaying;
                const catColor = COLORS[call.categoria] || "#64748b";
                const isDiv = Boolean(call.divergencia_tabulacao);

                return (
                  <tr
                    key={call.id}
                    className={`hover:bg-slate-800/40 transition group ${
                      playingCall?.id === call.id ? "bg-indigo-500/10" : ""
                    }`}
                  >
                    {/* Botão Play Individual */}
                    <td className="py-3 px-2 text-center">
                      <button
                        onClick={() => playCall(call)}
                        disabled={!call.tem_audio}
                        title={call.tem_audio ? "Ouvir gravação" : "Áudio não disponível"}
                        className={`w-8 h-8 rounded-full flex items-center justify-center transition mx-auto ${
                          isCurrentPlaying
                            ? "bg-indigo-500 text-white shadow-lg shadow-indigo-500/30"
                            : call.tem_audio
                            ? "bg-slate-800 text-indigo-400 hover:bg-indigo-600 hover:text-white"
                            : "bg-slate-900 text-slate-600 cursor-not-allowed"
                        }`}
                      >
                        {isCurrentPlaying ? (
                          <Pause size={14} className="fill-current" />
                        ) : (
                          <Play size={14} className="fill-current ml-0.5" />
                        )}
                      </button>
                    </td>

                    {/* Data / Hora */}
                    <td className="py-3 px-3 text-slate-300 font-mono whitespace-nowrap">
                      {fmtDate(call.data_ligacao)}
                    </td>

                    {/* Tronco / Agente */}
                    <td className="py-3 px-3 whitespace-nowrap">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="px-2 py-0.5 rounded-full font-bold text-[10px] bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                          {call.tronco?.split(" - ")[0] || "ARGUS"}
                        </span>
                        {call.tipo_agente && (
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                              call.tipo_agente === "DIGITAL"
                                ? "bg-purple-500/20 text-purple-300"
                                : "bg-slate-800 text-slate-300"
                            }`}
                          >
                            {call.tipo_agente}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Operador */}
                    <td className="py-3 px-3">
                      <div className="font-semibold text-white truncate max-w-[170px]" title={call.operador_nome}>
                        {call.operador_nome || "Não Identificado"}
                      </div>
                      {call.grupo_origem && (
                        <div className="text-[10px] text-slate-400 truncate max-w-[170px]" title={call.grupo_origem}>
                          {call.grupo_origem}
                        </div>
                      )}
                    </td>

                    {/* Cliente / Telefone */}
                    <td className="py-3 px-3">
                      <div
                        className="font-semibold text-slate-200 truncate max-w-[180px]"
                        title={call.cliente_identificado || call.nome_esperado}
                      >
                        {call.cliente_identificado || call.nome_esperado || "Não Informado"}
                      </div>
                      <div className="text-[11px] text-slate-400 font-mono">
                        {call.telefone || "-"}
                      </div>
                    </td>

                    {/* Desligado Por (SIP) */}
                    <td className="py-3 px-3 text-center whitespace-nowrap">
                      {call.desligado_por === "CLIENTE" ? (
                        <span
                          className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-bold text-[10px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                          title={call.desligamento_detalhe || "BYE recebido da operadora/cliente"}
                        >
                          <PhoneOff size={11} />
                          CLIENTE
                        </span>
                      ) : call.desligado_por === "OPERADOR" ? (
                        <span
                          className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-bold text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/40"
                          title={call.desligamento_detalhe || "BYE enviado pelo operador"}
                        >
                          <PhoneOff size={11} />
                          OPERADOR
                        </span>
                      ) : (
                        <span className="text-slate-500 font-mono text-[10px]">
                          {call.desligado_por || "-"}
                        </span>
                      )}
                    </td>

                    {/* Contraste Tabulação vs IA */}
                    <td className="py-3 px-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span
                            className="px-2 py-0.5 rounded-full text-[10px] font-bold border"
                            style={{
                              background: catColor + "22",
                              color: catColor,
                              borderColor: catColor + "44",
                            }}
                          >
                            {call.categoria_label || call.categoria || "Pendente"}
                          </span>

                          {isDiv && (
                            <span
                              className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse"
                              title={call.divergencia_detalhe || "Tabulação divergente da fala real"}
                            >
                              ⚠️ Divergente
                            </span>
                          )}
                        </div>

                        <div className="text-[10px] text-slate-400 truncate max-w-[220px]" title={call.tabulacao_operador}>
                          Op: <strong className="text-slate-300">{call.tabulacao_operador || "Sem tabulação"}</strong>
                        </div>
                      </div>
                    </td>

                    {/* Duração */}
                    <td className="py-3 px-2 text-right font-mono text-slate-300 whitespace-nowrap">
                      {fmtDur(call.duracao_segundos)}
                    </td>

                    {/* Botão de Detalhes */}
                    <td className="py-3 px-3 text-center whitespace-nowrap">
                      <button
                        onClick={() => setSel(call.id)}
                        className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition font-medium flex items-center gap-1 mx-auto text-[11px]"
                      >
                        <FileText size={12} />
                        Auditar
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {/* Paginação */}
        {data.total > PAGE_SIZE && (
          <div className="flex items-center justify-between p-4 border-t border-slate-800 text-xs">
            <span className="text-slate-400 font-mono">
              Mostrando {(page - 1) * PAGE_SIZE + 1} a{" "}
              {Math.min(page * PAGE_SIZE, data.total)} de {data.total}
            </span>

            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 disabled:opacity-40 hover:bg-slate-700"
              >
                Anterior
              </button>
              <button
                disabled={page * PAGE_SIZE >= data.total}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 disabled:opacity-40 hover:bg-slate-700"
              >
                Próxima
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal / Drawer com Detalhes Auditados */}
      {sel && (
        <AudioDrawer
          id={sel}
          onClose={() => setSel(null)}
          onOpen={(newId) => setSel(newId)}
        />
      )}

      {/* Player Fixo Flutuante na Parte Inferior */}
      <GlobalBottomPlayer
        call={playingCall}
        isPlaying={isPlaying}
        currentTime={currentTime}
        duration={duration}
        speed={speed}
        onTogglePlay={togglePlay}
        onSeek={handleSeek}
        onSeekRelative={seekRelative}
        onPrev={handlePlayPrev}
        onNext={handlePlayNext}
        onSetSpeed={handleSpeedChange}
        onOpenModal={() => setSel(playingCall?.id)}
        onClose={() => {
          if (globalAudioRef.current) {
            globalAudioRef.current.pause();
            globalAudioRef.current.src = "";
          }
          setPlayingCall(null);
          setIsPlaying(false);
        }}
      />
    </div>
  );
}
