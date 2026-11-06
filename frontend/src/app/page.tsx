"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import DateFilter from "@/components/DateFilter";
import GlobalBottomPlayer from "@/components/GlobalBottomPlayer";
import AudioDrawer from "@/components/AudioDrawer";
import { API, COLORS, fmtDate, fmtDur, formatTime, get, post, qs, exportCsvUrl } from "@/lib/api";
import {
  Play,
  Pause,
  Download,
  RefreshCw,
  FolderOpen,
  Sparkles,
  Search,
  Volume2,
  FileText,
  AlertCircle,
  AlertTriangle,
  PhoneOff,
  User,
  Headphones,
  CheckCircle2,
  XCircle,
  Filter,
  RotateCcw,
  Bot,
  UserCheck,
  Users,
} from "lucide-react";

export default function Dashboard() {
  // Filtros Avançados para o Analista de Dados
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [tronco, setTronco] = useState("");
  const [tipoAgente, setTipoAgente] = useState("");
  const [tipoDiscagem, setTipoDiscagem] = useState("");
  const [desligadoPor, setDesligadoPor] = useState("");
  const [divergencia, setDivergencia] = useState("");
  const [operador, setOperador] = useState("");
  const [categoria, setCategoria] = useState("");
  const [subcategoria, setSubcategoria] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 50;

  // Dados do backend
  const [summary, setSummary] = useState<any>(null);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [callsData, setCallsData] = useState<{ items: any[]; total: number }>({
    items: [],
    total: 0,
  });
  const [tax, setTax] = useState<any>({});
  const [filterOpts, setFilterOpts] = useState<any>({
    operadores: [],
    troncos: [],
    tipos_agente: ["COMERCIAL", "DIGITAL"],
    tipos_discagem: ["ATIVO", "URA"],
    desligado_por: ["CLIENTE", "OPERADOR"],
    categorias: [],
  });

  // Estados de execução
  const [loading, setLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  // Player de Áudio Global
  const [playingCall, setPlayingCall] = useState<any>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeed] = useState(1.0);
  const [selectedCallId, setSelectedCallId] = useState<number | null>(null);
  const globalAudioRef = useRef<HTMLAudioElement | null>(null);

  // Inicializa o elemento de áudio global
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

  // Atalhos de teclado (Espaço, Seta Esquerda, Seta Direita)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.code === "Space") {
        e.preventDefault();
        togglePlay();
      } else if (e.code === "ArrowLeft") {
        seekRelative(-5);
      } else if (e.code === "ArrowRight") {
        seekRelative(5);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [playingCall, isPlaying]);

  // Carrega opções de filtro do analista e taxonomia
  useEffect(() => {
    get<any>("/api/v1/taxonomy").then(setTax).catch(() => {});
    get<any>("/api/v1/analyst/filters-options").then(setFilterOpts).catch(() => {});
  }, []);

  // Limpar filtros
  const handleResetFilters = () => {
    setIni("");
    setFim("");
    setTronco("");
    setTipoAgente("");
    setTipoDiscagem("");
    setDesligadoPor("");
    setDivergencia("");
    setOperador("");
    setCategoria("");
    setSubcategoria("");
    setSearch("");
    setPage(1);
  };

  // Carrega métricas do dashboard e tabela de chamadas
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const filterParams: Record<string, any> = {
        data_inicio: ini,
        data_fim: fim,
        tronco,
        tipo_agente: tipoAgente,
        tipo_discagem: tipoDiscagem,
        desligado_por: desligadoPor,
        divergencia: divergencia === "" ? undefined : divergencia === "true",
        operador,
        categoria,
        subcategoria,
        q: search,
      };

      const [s, tl, cl] = await Promise.all([
        get<any>("/api/v1/analytics/summary", filterParams),
        get<any[]>("/api/v1/analytics/timeline", {
          data_inicio: ini,
          data_fim: fim,
          tronco,
          tipo_agente: tipoAgente,
          tipo_discagem: tipoDiscagem,
          desligado_por: desligadoPor,
        }),
        get<any>("/api/v1/calls", { ...filterParams, page, page_size: pageSize }),
      ]);

      setSummary(s);
      setTimeline(tl);
      setCallsData(cl);
      setErrorMsg("");
    } catch (e: any) {
      setErrorMsg(`Erro de comunicação com o backend (${e.message}).`);
    } finally {
      setLoading(false);
    }
  }, [ini, fim, tronco, tipoAgente, tipoDiscagem, desligadoPor, divergencia, operador, categoria, subcategoria, search, page]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 20000);
    return () => clearInterval(interval);
  }, [loadData]);

  // Ações de sincronização
  const runAction = async (label: string, path: string, params: any = {}) => {
    setActionMsg(`${label}...`);
    try {
      const res = await post(path, params);
      setActionMsg(`${label} concluído: ${JSON.stringify(res)}`);
      loadData();
      get<any>("/api/v1/analyst/filters-options").then(setFilterOpts).catch(() => {});
    } catch (e: any) {
      setActionMsg(`${label} falhou: ${e.message}`);
    }
  };

  // Funções do Player de Áudio
  const playCall = (item: any) => {
    const a = globalAudioRef.current;
    if (!a) return;

    if (playingCall?.id === item.id) {
      if (a.paused) {
        a.play().catch(() => {});
      } else {
        a.pause();
      }
      return;
    }

    setPlayingCall(item);
    const audioUrl = `${API}/api/v1/calls/${item.id}/audio`;
    a.src = audioUrl;
    a.playbackRate = speed;
    a.play().catch((err) => {
      console.warn("Autoplay bloqueado:", err);
    });
  };

  const togglePlay = () => {
    const a = globalAudioRef.current;
    if (!a) return;
    if (!playingCall && callsData.items.length > 0) {
      playCall(callsData.items[0]);
      return;
    }
    if (a.paused) {
      a.play().catch(() => {});
    } else {
      a.pause();
    }
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
    if (globalAudioRef.current) {
      globalAudioRef.current.playbackRate = s;
    }
  };

  const handlePlayNext = () => {
    if (!playingCall || callsData.items.length === 0) return;
    const curIdx = callsData.items.findIndex((c) => c.id === playingCall.id);
    if (curIdx >= 0 && curIdx < callsData.items.length - 1) {
      playCall(callsData.items[curIdx + 1]);
    }
  };

  const handlePlayPrev = () => {
    if (!playingCall || callsData.items.length === 0) return;
    const curIdx = callsData.items.findIndex((c) => c.id === playingCall.id);
    if (curIdx > 0) {
      playCall(callsData.items[curIdx - 1]);
    }
  };

  // Helper dos dados estatísticos
  const total = summary?.total ?? 0;
  const qualificadas = summary?.qualificadas ?? 0;
  const getCatCount = (catCode: string) =>
    summary?.categorias?.find((c: any) => c.codigo === catCode)?.total ?? 0;
  const getCatPct = (catCode: string) =>
    summary?.categorias?.find((c: any) => c.codigo === catCode)?.pct ?? 0;

  // Estatísticas Analíticas
  const desligCliente = summary?.desligamentos?.find((d: any) => d.tipo === "CLIENTE");
  const desligOperador = summary?.desligamentos?.find((d: any) => d.tipo === "OPERADOR");
  const agenteComercial = summary?.agentes?.find((a: any) => a.tipo === "COMERCIAL");
  const agenteDigital = summary?.agentes?.find((a: any) => a.tipo === "DIGITAL");
  const discAtivo = summary?.discagens?.find((d: any) => d.tipo === "ATIVO");
  const discUra = summary?.discagens?.find((d: any) => d.tipo === "URA");
  const divergencias = summary?.divergencias ?? { total: 0, taxa: 0 };

  const tronco4Net = summary?.troncos?.find((t: any) => t.tronco?.includes("4NET"))?.total ?? 0;
  const troncoVenditore = summary?.troncos?.find((t: any) => t.tronco?.includes("VENDITORE"))?.total ?? 0;

  const currentFiltersObj = {
    data_inicio: ini,
    data_fim: fim,
    tronco,
    tipo_agente: tipoAgente,
    tipo_discagem: tipoDiscagem,
    desligado_por: desligadoPor,
    divergencia: divergencia === "" ? undefined : divergencia === "true",
    operador,
    categoria,
    subcategoria,
    q: search,
  };

  return (
    <div className="space-y-6 pb-28">
      {/* Header Executivo & Ações */}
      <header className="border-b border-slate-800 pb-5">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Observabilidade Argus · {qualificadas} Chamadas Auditadas
            </div>
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white flex items-center gap-2.5">
              <span>🎧 Supervisor Argus</span>
              <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-indigo-600/30 text-indigo-300 border border-indigo-500/30">
                OpenAI IA Ativa
              </span>
            </h1>
            <p className="text-slate-400 text-xs mt-1">
              Auditoria fonética, contraste de tabulação, análise de desligamento (SIP) e qualificação em tempo real.
            </p>
          </div>

          {/* Botões de Ação */}
          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={() => runAction("Importar Acervo Local & Cruzar Dados", "/api/v1/sync/local")}
              className="btn-ghost"
              title="Sincroniza pasta Gravações e cruza metadados de cruzar_dados.csv"
            >
              <FolderOpen size={14} className="text-indigo-400" />
              <span>Importar & Cruzar Dados</span>
            </button>

            <button
              onClick={() =>
                runAction("Sincronizar Argus", "/api/v1/sync/argus", {
                  ultimos_minutos: 15,
                })
              }
              className="btn-ghost"
              title="Busca ligações recentes da API Argus em tempo real"
            >
              <RefreshCw size={14} className="text-sky-400" />
              <span>Sincronizar Argus</span>
            </button>

            <button
              onClick={() => runAction("Qualificar com IA", "/api/v1/sync/process")}
              className="btn"
              title="Processa chamadas pendentes com OpenAI ChatGPT e Whisper"
            >
              <Sparkles size={14} />
              <span>Qualificar com OpenAI</span>
            </button>

            <a
              href={exportCsvUrl(currentFiltersObj)}
              download
              className="px-3 py-2 rounded-xl text-xs font-semibold bg-emerald-600/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-600/30 transition flex items-center gap-1.5"
              title="Exporta todas as ligações do filtro atual em formato CSV compatível com Excel"
            >
              <Download size={14} />
              <span>Exportar Relatório CSV</span>
            </a>
          </div>
        </div>
      </header>

      {/* Barra de Notificações / Status */}
      {actionMsg && (
        <div className="p-3 rounded-xl bg-slate-900 border border-indigo-500/30 text-xs text-indigo-300 flex items-center justify-between">
          <span className="truncate">{actionMsg}</span>
          <button onClick={() => setActionMsg("")} className="text-slate-400 hover:text-white ml-2">
            ✕
          </button>
        </div>
      )}

      {errorMsg && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300 flex items-center gap-2">
          <AlertCircle size={16} className="text-rose-400 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* PAINEL DE FILTROS AVANÇADOS DO ANALISTA */}
      <section className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 shadow-xl space-y-3.5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2 text-white font-semibold text-xs">
            <Filter size={15} className="text-indigo-400" />
            <span>Filtros do Analista de Dados & Validação de Autenticidade</span>
          </div>

          <div className="flex items-center gap-2">
            {(ini || fim || tronco || tipoAgente || tipoDiscagem || desligadoPor || divergencia || operador || categoria || search) && (
              <button
                onClick={handleResetFilters}
                className="text-xs text-slate-400 hover:text-rose-400 flex items-center gap-1 transition px-2 py-1 rounded bg-slate-800/60"
              >
                <RotateCcw size={12} />
                <span>Limpar Filtros</span>
              </button>
            )}
            <span className="text-xs text-slate-400 font-mono">
              Exibindo <strong>{callsData.total}</strong> chamadas
            </span>
          </div>
        </div>

        {/* Linha 1 de Filtros: Período, Busca e Tronco */}
        <div className="grid grid-cols-1 md:grid-cols-4 lg:grid-cols-6 gap-2.5 text-xs">
          {/* Seletor de Data */}
          <div className="md:col-span-2">
            <DateFilter ini={ini} fim={fim} onChange={(i, f) => { setIni(i); setFim(f); setPage(1); }} />
          </div>

          {/* Busca Textual */}
          <div className="md:col-span-2 relative">
            <Search size={14} className="absolute left-3 top-3 text-slate-500" />
            <input
              type="text"
              placeholder="Buscar cliente, tel, operador, transcrição..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-9 pr-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* Tronco */}
          <div>
            <select
              value={tronco}
              onChange={(e) => { setTronco(e.target.value); setPage(1); }}
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

          {/* Operador */}
          <div>
            <select
              value={operador}
              onChange={(e) => { setOperador(e.target.value); setPage(1); }}
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

        {/* Linha 2 de Filtros Especializados: Agente, Discagem, Desligamento, Divergência e Categoria */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5 text-xs pt-1">
          {/* Tipo de Agente */}
          <div>
            <select
              value={tipoAgente}
              onChange={(e) => { setTipoAgente(e.target.value); setPage(1); }}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500"
            >
              <option value="">Equipe: Comercial / Digital</option>
              <option value="COMERCIAL">COMERCIAL (Equipe Comercial)</option>
              <option value="DIGITAL">DIGITAL (Equipe Digital)</option>
            </select>
          </div>

          {/* Origem da Discagem */}
          <div>
            <select
              value={tipoDiscagem}
              onChange={(e) => { setTipoDiscagem(e.target.value); setPage(1); }}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500"
            >
              <option value="">Discagem: Ativo / URA</option>
              <option value="ATIVO">ATIVO (Preditivo/Manual)</option>
              <option value="URA">URA (Receptivo/Direcionado)</option>
            </select>
          </div>

          {/* Desligado Por (SIP) */}
          <div>
            <select
              value={desligadoPor}
              onChange={(e) => { setDesligadoPor(e.target.value); setPage(1); }}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500"
            >
              <option value="">Desligado Por: Todos</option>
              <option value="CLIENTE">CLIENTE (BYE recebido)</option>
              <option value="OPERADOR">OPERADOR (BYE enviado)</option>
            </select>
          </div>

          {/* Auditoria de Fidelidade / Divergência */}
          <div>
            <select
              value={divergencia}
              onChange={(e) => { setDivergencia(e.target.value); setPage(1); }}
              className={`w-full border rounded-xl px-3 py-2 text-white focus:outline-none ${
                divergencia === "true"
                  ? "bg-amber-950/60 border-amber-500/60 text-amber-200"
                  : "bg-slate-950 border-slate-800"
              }`}
            >
              <option value="">Auditoria: Todas Chamadas</option>
              <option value="true">⚠️ Com Divergência de Tabulação</option>
              <option value="false">✓ Sem Divergência (Alinhadas)</option>
            </select>
          </div>

          {/* Categoria IA */}
          <div>
            <select
              value={categoria}
              onChange={(e) => { setCategoria(e.target.value); setPage(1); }}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white focus:outline-none focus:border-indigo-500"
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
      </section>

      {/* CARDS DE INSIGHTS & AUDITORIA OPERACIONAL */}
      <section className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        {/* Card 1: Divergência de Tabulação (Auditoria) */}
        <div
          onClick={() => { setDivergencia(divergencia === "true" ? "" : "true"); setPage(1); }}
          className={`card cursor-pointer transition border ${
            divergencia === "true"
              ? "border-amber-500 bg-amber-500/20 shadow-lg shadow-amber-500/10"
              : "border-amber-500/40 bg-amber-500/5 hover:border-amber-400"
          }`}
          title="Clique para filtrar apenas as chamadas com tabulação humana divergente da gravação real"
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-amber-400 uppercase tracking-wider flex items-center gap-1">
              <AlertTriangle size={13} />
              Divergência
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold">
              {divergencias.taxa}%
            </span>
          </div>
          <div className="text-2xl font-bold mt-1 text-amber-300">{divergencias.total}</div>
          <span className="text-[10px] text-amber-400/80">Tabulação incorreta ou omitida</span>
        </div>

        {/* Card 2: Desligamento (Quem Desligou?) */}
        <div className="card border-cyan-500/30 bg-cyan-500/5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-cyan-400 uppercase tracking-wider flex items-center gap-1">
              <PhoneOff size={13} />
              Desligamento
            </span>
            <span className="text-[10px] text-cyan-300 font-bold">
              {desligCliente?.pct ?? 0}% Cliente
            </span>
          </div>
          <div className="text-lg font-bold mt-1 text-white flex items-center justify-between">
            <span className="text-cyan-400">{desligCliente?.total ?? 0}</span>
            <span className="text-xs text-slate-500">vs</span>
            <span className="text-slate-300">{desligOperador?.total ?? 0}</span>
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-1.5 overflow-hidden flex">
            <div
              className="bg-cyan-400 h-full"
              style={{ width: `${desligCliente?.pct ?? 50}%` }}
              title={`Cliente: ${desligCliente?.pct ?? 0}%`}
            />
            <div
              className="bg-amber-400 h-full"
              style={{ width: `${desligOperador?.pct ?? 50}%` }}
              title={`Operador: ${desligOperador?.pct ?? 0}%`}
            />
          </div>
          <div className="flex justify-between text-[9px] text-slate-400 mt-1">
            <span>Cliente ({desligCliente?.pct ?? 0}%)</span>
            <span>Operador ({desligOperador?.pct ?? 0}%)</span>
          </div>
        </div>

        {/* Card 3: Comercial vs Digital */}
        <div className="card border-purple-500/30 bg-purple-500/5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-purple-400 uppercase tracking-wider flex items-center gap-1">
              <Users size={13} />
              Célula Operacional
            </span>
            <span className="text-[10px] text-purple-300 font-bold">
              {agenteComercial?.pct ?? 0}% Comercial
            </span>
          </div>
          <div className="text-lg font-bold mt-1 text-white flex items-center justify-between">
            <span className="text-purple-300">{agenteComercial?.total ?? 0}</span>
            <span className="text-xs text-slate-500">vs</span>
            <span className="text-purple-400">{agenteDigital?.total ?? 0}</span>
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-1.5 overflow-hidden flex">
            <div
              className="bg-purple-400 h-full"
              style={{ width: `${agenteComercial?.pct ?? 70}%` }}
              title={`Equipe Comercial: ${agenteComercial?.pct ?? 0}%`}
            />
            <div
              className="bg-purple-600 h-full"
              style={{ width: `${agenteDigital?.pct ?? 30}%` }}
              title={`Equipe Digital: ${agenteDigital?.pct ?? 0}%`}
            />
          </div>
          <div className="flex justify-between text-[9px] text-slate-400 mt-1">
            <span>Comercial ({agenteComercial?.pct ?? 0}%)</span>
            <span>Digital ({agenteDigital?.pct ?? 0}%)</span>
          </div>
        </div>

        {/* Card 4: Discagem Ativo vs URA */}
        <div className="card border-blue-500/30 bg-blue-500/5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-blue-400 uppercase tracking-wider flex items-center gap-1">
              <Headphones size={13} />
              Discagem
            </span>
            <span className="text-[10px] text-blue-300 font-bold">
              {discAtivo?.pct ?? 0}% Ativo
            </span>
          </div>
          <div className="text-lg font-bold mt-1 text-white flex items-center justify-between">
            <span className="text-blue-400">{discAtivo?.total ?? 0}</span>
            <span className="text-xs text-slate-500">vs</span>
            <span className="text-indigo-300">{discUra?.total ?? 0}</span>
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full mt-1.5 overflow-hidden flex">
            <div
              className="bg-blue-400 h-full"
              style={{ width: `${discAtivo?.pct ?? 80}%` }}
            />
            <div
              className="bg-indigo-400 h-full"
              style={{ width: `${discUra?.pct ?? 20}%` }}
            />
          </div>
          <div className="flex justify-between text-[9px] text-slate-400 mt-1">
            <span>Ativo ({discAtivo?.pct ?? 0}%)</span>
            <span>URA ({discUra?.pct ?? 0}%)</span>
          </div>
        </div>

        {/* Card 5: Em Negociação (Qualificação Real) */}
        <div
          onClick={() => { setCategoria(categoria === "EM_NEGOCIACAO" ? "" : "EM_NEGOCIACAO"); setPage(1); }}
          className={`card cursor-pointer transition border ${
            categoria === "EM_NEGOCIACAO"
              ? "border-emerald-500 bg-emerald-500/20"
              : "border-emerald-500/30 bg-emerald-500/5 hover:border-emerald-400"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider">
              Em Negociação
            </span>
            <span className="text-[10px] text-emerald-300 font-bold">{getCatPct("EM_NEGOCIACAO")}%</span>
          </div>
          <div className="text-2xl font-bold mt-1 text-emerald-400">{getCatCount("EM_NEGOCIACAO")}</div>
          <span className="text-[10px] text-slate-400">Propostas e valores discutidos</span>
        </div>

        {/* Card 6: Total Gravado & Média */}
        <div className="card">
          <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Total Auditado</span>
          <div className="text-2xl font-bold mt-1 text-white">{total}</div>
          <span className="text-[10px] text-slate-400">
            {summary?.duracao_total_horas ?? 0}h ({summary?.duracao_media ?? 0}s média)
          </span>
        </div>
      </section>

      {/* CONTRASTE: TABULAÇÃO OPERADOR VS QUALIFICAÇÃO IA & RANKING */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Matriz de Contraste de Tabulações */}
        <div className="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <AlertTriangle size={16} className="text-amber-400" />
                Matriz de Contraste: Tabulação do Operador vs Qualificação IA
              </h3>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Comparativo direto do que os operadores registraram versus o que a IA auditou no áudio.
              </p>
            </div>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">
              Top 10 Tabulações
            </span>
          </div>

          <div className="overflow-x-auto text-xs">
            <table className="w-full text-left">
              <thead>
                <tr className="text-slate-400 border-b border-slate-800/80">
                  <th className="py-2 px-3 font-semibold">Tabulação no Argus (Operador)</th>
                  <th className="py-2 px-2 text-center font-semibold">Total</th>
                  <th className="py-2 px-2 text-center font-semibold text-emerald-400">Em Negociação</th>
                  <th className="py-2 px-2 text-center font-semibold text-purple-400">Não é Cliente</th>
                  <th className="py-2 px-2 text-center font-semibold text-rose-400">Sem Interesse</th>
                  <th className="py-2 px-2 text-center font-semibold text-amber-400">Muda</th>
                  <th className="py-2 px-2 text-center font-semibold text-cyan-400">Caixa Postal</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {summary?.matriz_contraste?.map((item: any, idx: number) => {
                  const neg = item.categorias?.["EM_NEGOCIACAO"] || 0;
                  const naoCli = item.categorias?.["NAO_E_O_CLIENTE"] || 0;
                  const semInt = item.categorias?.["SEM_INTERESSE"] || 0;
                  const muda = item.categorias?.["LIGACAO_MUDA"] || 0;
                  const cx = item.categorias?.["CAIXA_POSTAL"] || 0;

                  return (
                    <tr key={idx} className="hover:bg-slate-800/40 transition">
                      <td className="py-2.5 px-3 font-medium text-slate-200">
                        {item.tabulacao_operador || "Não Tabulado"}
                      </td>
                      <td className="py-2.5 px-2 text-center font-bold text-white font-mono">
                        {item.total}
                      </td>
                      <td className={`py-2.5 px-2 text-center font-mono ${neg > 0 ? "text-emerald-400 font-bold bg-emerald-500/10 rounded" : "text-slate-500"}`}>
                        {neg || "-"}
                      </td>
                      <td className={`py-2.5 px-2 text-center font-mono ${naoCli > 0 ? "text-purple-400 font-bold bg-purple-500/10 rounded" : "text-slate-500"}`}>
                        {naoCli || "-"}
                      </td>
                      <td className={`py-2.5 px-2 text-center font-mono ${semInt > 0 ? "text-rose-400 font-bold bg-rose-500/10 rounded" : "text-slate-500"}`}>
                        {semInt || "-"}
                      </td>
                      <td className={`py-2.5 px-2 text-center font-mono ${muda > 0 ? "text-amber-400 font-bold bg-amber-500/10 rounded" : "text-slate-500"}`}>
                        {muda || "-"}
                      </td>
                      <td className={`py-2.5 px-2 text-center font-mono ${cx > 0 ? "text-cyan-400 font-bold bg-cyan-500/10 rounded" : "text-slate-500"}`}>
                        {cx || "-"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Ranking de Operadores por Taxa de Divergência */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
          <div className="border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Headphones size={16} className="text-indigo-400" />
              Auditoria por Operador
            </h3>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Operadores com maior volume e taxa de tabulações divergentes.
            </p>
          </div>

          <div className="space-y-2.5 overflow-y-auto max-h-80 pr-1 text-xs">
            {summary?.ranking_operadores?.map((op: any, i: number) => (
              <div
                key={i}
                onClick={() => { setOperador(op.operador); setPage(1); }}
                className="p-2.5 rounded-xl bg-slate-950/70 border border-slate-800 hover:border-indigo-500/50 cursor-pointer transition flex items-center justify-between"
                title={`Clique para filtrar ligações de ${op.operador}`}
              >
                <div className="truncate mr-2">
                  <div className="font-semibold text-slate-200 truncate">{op.operador}</div>
                  <div className="text-[10px] text-slate-400">
                    Total: {op.total} chamadas · {op.divergencias} divergências
                  </div>
                </div>

                <div className="text-right shrink-0">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-bold border ${
                      op.taxa_divergencia > 40
                        ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                        : op.taxa_divergencia > 25
                        ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                        : "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                    }`}
                  >
                    {op.taxa_divergencia}% erro
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* GRÁFICO HISTÓRICO TEMPORAL */}
      <section className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl">
        <h3 className="text-sm font-bold text-white mb-4">Volume Diário por Categoria Auditada</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={timeline} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="data" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#334155",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
              <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }} />
              {Object.keys(COLORS).map((k) => (
                <Bar key={k} dataKey={k} name={tax[k]?.label || k} fill={COLORS[k]} stackId="a" />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* TABELA DE LIGAÇÕES DETALHADA COM INSIGHTS COMPLETOS */}
      <section className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-4">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 border-b border-slate-800 pb-4">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Volume2 size={18} className="text-indigo-400" />
              Ligações Auditadas com Player & Sinalização SIP
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Pressione <kbd className="px-1.5 py-0.5 bg-slate-800 rounded text-slate-300 font-mono text-[10px]">Espaço</kbd> para play/pause, <kbd className="px-1.5 py-0.5 bg-slate-800 rounded text-slate-300 font-mono text-[10px]">←</kbd> <kbd className="px-1.5 py-0.5 bg-slate-800 rounded text-slate-300 font-mono text-[10px]">→</kbd> para avançar/voltar.
            </p>
          </div>

          <div className="text-xs text-slate-400 font-mono">
            Página {page} de {Math.max(1, Math.ceil(callsData.total / pageSize))}
          </div>
        </div>

        {/* Tabela de Resultados */}
        <div className="overflow-x-auto text-xs">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 uppercase tracking-wider text-[11px]">
                <th className="py-3 px-2 text-center w-12">Áudio</th>
                <th className="py-3 px-3">Data / Hora</th>
                <th className="py-3 px-3">Tronco / Origem</th>
                <th className="py-3 px-3">Operador</th>
                <th className="py-3 px-3">Cliente / Telefone</th>
                <th className="py-3 px-3 text-center">Desligado Por</th>
                <th className="py-3 px-3">Contraste: Tabulação vs IA</th>
                <th className="py-3 px-2 text-right">Duração</th>
                <th className="py-3 px-3 text-center">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-sans">
              {callsData.items.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-slate-500 text-xs">
                    Nenhuma ligação encontrada com os filtros selecionados.
                  </td>
                </tr>
              ) : (
                callsData.items.map((call) => {
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

                      {/* Tronco / Origem / Agente */}
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
                          {call.tipo_discagem && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">
                              {call.tipo_discagem}
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

                      {/* Contraste: Tabulação Operador vs Qualificação IA */}
                      <td className="py-3 px-3">
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            {/* Categoria IA */}
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

                            {/* Badge Divergente em Alerta */}
                            {isDiv && (
                              <span
                                className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse"
                                title={call.divergencia_detalhe || "Tabulação divergente da fala real"}
                              >
                                ⚠️ Divergente
                              </span>
                            )}
                          </div>

                          {/* O que o operador registrou */}
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
                          onClick={() => setSelectedCallId(call.id)}
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
        </div>

        {/* Paginação */}
        {callsData.total > pageSize && (
          <div className="flex items-center justify-between border-t border-slate-800 pt-3 text-xs">
            <span className="text-slate-400 font-mono">
              Mostrando {(page - 1) * pageSize + 1} a{" "}
              {Math.min(page * pageSize, callsData.total)} de {callsData.total}
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
                disabled={page * pageSize >= callsData.total}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 disabled:opacity-40 hover:bg-slate-700"
              >
                Próxima
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Modal / Drawer com Detalhes Auditados */}
      {selectedCallId && (
        <AudioDrawer
          id={selectedCallId}
          onClose={() => setSelectedCallId(null)}
          onOpen={(newId) => setSelectedCallId(newId)}
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
        onOpenModal={() => setSelectedCallId(playingCall?.id)}
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
