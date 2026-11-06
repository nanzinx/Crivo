"use client";
import { useEffect, useState, useRef } from "react";
import {
  X,
  Play,
  Pause,
  AlertTriangle,
  Sparkles,
  RefreshCw,
  PhoneOff,
  User,
  Headphones,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Zap,
} from "lucide-react";
import { API, COLORS, fmtDate, fmtDur, get, post } from "@/lib/api";

export default function AudioDrawer({
  id,
  onClose,
  onOpen,
}: {
  id: number;
  onClose: () => void;
  onOpen: (id: number) => void;
}) {
  const [c, setC] = useState<any>(null);
  const [speed, setSpeed] = useState(1.0);
  const [reprocessing, setReprocessing] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    setC(null);
    get(`/api/v1/calls/${id}`).then(setC);
  }, [id]);

  const handleSpeed = (s: number) => {
    setSpeed(s);
    if (audioRef.current) audioRef.current.playbackRate = s;
  };

  const handleReprocess = async () => {
    if (!c) return;
    setReprocessing(true);
    try {
      await post(`/api/v1/sync/reprocess/${c.id}`);
      const updated = await get(`/api/v1/calls/${c.id}`);
      setC(updated);
    } catch (e: any) {
      alert("Erro ao reprocessar: " + e.message);
    } finally {
      setReprocessing(false);
    }
  };

  if (!c) return null;
  const ref = c.ligacao_referencia;
  const catColor = COLORS[c.categoria] || "#64748b";
  const tronco = c.tronco ? c.tronco.split(" - ")[0] : "ARGUS";

  const isDivergent = Boolean(c.divergencia_tabulacao);
  const desligouCliente = c.desligado_por === "CLIENTE";
  const desligouOperador = c.desligado_por === "OPERADOR";

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl relative space-y-4 max-h-[92vh] flex flex-col">
        {/* Header do Modal */}
        <div className="flex items-start justify-between border-b border-slate-800 pb-4 shrink-0">
          <div>
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="text-xs px-2.5 py-0.5 rounded-full font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                {tronco}
              </span>
              <span
                className="text-xs px-2.5 py-0.5 rounded-full font-semibold border"
                style={{
                  background: catColor + "22",
                  color: catColor,
                  borderColor: catColor + "44",
                }}
              >
                {c.categoria_label || c.categoria}
              </span>
              {c.tipo_agente && (
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium border ${
                    c.tipo_agente === "DIGITAL"
                      ? "bg-purple-500/10 text-purple-300 border-purple-500/30"
                      : "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
                  }`}
                >
                  Equipe {c.tipo_agente}
                </span>
              )}
              {c.tipo_discagem && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                  {c.tipo_discagem}
                </span>
              )}
              {c.sentimento_cliente && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                  Cliente {c.sentimento_cliente}
                </span>
              )}
            </div>

            <h3 className="text-lg font-bold text-white mt-1">
              {c.cliente_identificado || c.nome_esperado || "Cliente Não Informado"}
            </h3>
            <p className="text-xs text-slate-400 font-mono">
              Tel: {c.telefone || "N/A"} · Chamada #{c.id_ligacao || c.id} · {fmtDate(c.data_ligacao)}
            </p>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-lg bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Conteúdo com Scroll */}
        <div className="space-y-4 text-xs overflow-y-auto pr-1">
          {/* Card de Alerta de Divergência de Tabulação */}
          {isDivergent ? (
            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/40 text-amber-200 space-y-1">
              <div className="flex items-center gap-2 font-bold text-amber-400 text-xs">
                <AlertTriangle size={15} />
                <span>DIVERGÊNCIA DE TABULAÇÃO AUDITADA</span>
              </div>
              <p className="text-xs leading-relaxed text-amber-100">
                {c.divergencia_detalhe ||
                  `O operador tabulou como "${c.tabulacao_operador}", porém a IA identificou "${c.categoria_label || c.categoria}".`}
              </p>
            </div>
          ) : (
            c.tabulacao_operador && (
              <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 flex items-center gap-2 text-xs">
                <CheckCircle2 size={15} className="text-emerald-400 shrink-0" />
                <span>
                  Tabulação Coerente: Operador ({c.tabulacao_operador}) alinhado com IA (
                  {c.categoria_label || c.categoria}).
                </span>
              </div>
            )
          )}

          {/* Destaque Quem Desligou a Chamada (SIP Signaling) */}
          <div className="grid grid-cols-2 gap-2.5 bg-slate-950/80 p-3 rounded-xl border border-slate-800">
            <div>
              <span className="text-slate-400 block mb-0.5">Desligado por:</span>
              <div className="flex items-center gap-1.5 font-bold text-sm">
                <PhoneOff
                  size={15}
                  className={
                    desligouCliente ? "text-cyan-400" : desligouOperador ? "text-amber-400" : "text-slate-400"
                  }
                />
                <span
                  className={
                    desligouCliente ? "text-cyan-400" : desligouOperador ? "text-amber-400" : "text-slate-300"
                  }
                >
                  {c.desligado_por || "DESCONHECIDO"}
                </span>
              </div>
              <span className="text-[10px] text-slate-400 font-mono mt-0.5 block">
                {c.desligamento_detalhe || "Sinalização SIP indisponível"}
              </span>
            </div>

            <div>
              <span className="text-slate-400 block mb-0.5">Operador Responsável:</span>
              <div className="flex items-center gap-1.5 font-semibold text-slate-200">
                <Headphones size={15} className="text-indigo-400 shrink-0" />
                <span className="truncate">{c.operador_nome || c.operador_id || "Não Identificado"}</span>
              </div>
              {c.tempo_reacao_operador !== null && c.tempo_reacao_operador !== undefined && (
                <span className="text-[10px] text-slate-400 block mt-0.5">
                  Tempo de reação: {c.tempo_reacao_operador}s
                </span>
              )}
            </div>
          </div>

          {/* Card do Player de Áudio */}
          <div className="p-3.5 rounded-xl bg-slate-950 border border-indigo-500/30 space-y-2.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-indigo-400 flex items-center gap-1.5">
                <Play size={14} className="fill-indigo-400" />
                Gravação de Áudio
              </span>
              <div className="flex items-center gap-1 text-[11px]">
                <span className="text-slate-400 mr-1">Velocidade:</span>
                {[1.0, 1.25, 1.5, 2.0].map((s) => (
                  <button
                    key={s}
                    onClick={() => handleSpeed(s)}
                    className={`px-1.5 py-0.5 rounded transition ${
                      speed === s
                        ? "bg-indigo-600 text-white font-bold"
                        : "bg-slate-800 text-slate-300 hover:text-white"
                    }`}
                  >
                    {s}x
                  </button>
                ))}
              </div>
            </div>

            {c.tem_audio ? (
              <audio
                ref={audioRef}
                controls
                className="w-full h-9 rounded outline-none"
                src={`${API}/api/v1/calls/${c.id}/audio`}
              />
            ) : (
              <p className="text-xs text-slate-500 italic">Arquivo de áudio não disponível fisicamente no servidor.</p>
            )}
          </div>

          {/* Alerta de conflito de identidade (Regra É o Cliente) */}
          {c.conflito_identidade && (
            <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/30 text-purple-200 flex items-start gap-2.5">
              <AlertTriangle size={18} className="text-purple-400 shrink-0 mt-0.5" />
              <div>
                <strong className="font-bold text-white block">Regra Ativa: Titular Confirmado em Histórico</strong>
                A pessoa nesta ligação alegou não ser o cliente, porém o titular já atendeu e confirmou seu nome neste
                mesmo número anteriormente.
                {ref && (
                  <button
                    onClick={() => onOpen(ref.id)}
                    className="block mt-1 text-purple-300 underline hover:text-white font-semibold"
                  >
                    Ver ligação de confirmação ({fmtDate(ref.data_ligacao)}) →
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Grid de Metadados da Chamada */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2.5 bg-slate-950/60 p-3 rounded-xl border border-slate-800">
            <div>
              <span className="text-slate-400">Subcategoria:</span>
              <div className="font-semibold text-slate-200 mt-0.5">
                {c.subcategoria_label || c.subcategoria || "-"}
              </div>
            </div>
            <div>
              <span className="text-slate-400">Duração:</span>
              <div className="font-semibold text-slate-200 mt-0.5">
                {c.duracao_segundos ? `${c.duracao_segundos}s (${fmtDur(c.duracao_segundos)})` : "-"}
              </div>
            </div>
            <div>
              <span className="text-slate-400">Grupo de Origem:</span>
              <div className="font-semibold text-slate-200 mt-0.5 truncate">{c.grupo_origem || "-"}</div>
            </div>
            <div>
              <span className="text-slate-400">Tabulação Operador:</span>
              <div className="font-semibold text-slate-200 mt-0.5">{c.tabulacao_operador || "-"}</div>
            </div>
            <div>
              <span className="text-slate-400">Motor IA:</span>
              <div className="font-semibold text-indigo-300 mt-0.5 capitalize flex items-center gap-1">
                <Sparkles size={12} />
                {c.motor || "offline"} {c.confianca ? `(${Math.round(c.confianca * 100)}%)` : ""}
              </div>
            </div>
            <div>
              <span className="text-slate-400">Tronco:</span>
              <div className="font-semibold text-slate-200 mt-0.5">{c.tronco || "-"}</div>
            </div>
            <div className="col-span-2 md:col-span-3">
              <span className="text-slate-400">Arquivo Gravação:</span>
              <div className="font-mono text-[11px] text-sky-400 mt-0.5 break-all select-all">
                {c.nome_arquivo || "-"}
              </div>
            </div>
          </div>

          {/* Resumo da IA */}
          {c.resumo && (
            <div className="bg-slate-950/40 p-3 rounded-lg border border-slate-800">
              <span className="font-semibold text-slate-300 block mb-1">Parecer da IA / Justificativa:</span>
              <p className="text-slate-300 text-xs leading-relaxed">{c.resumo}</p>
            </div>
          )}

          {/* Evidência da Fala */}
          {c.evidencia && (
            <div className="bg-slate-950/40 p-3 rounded-lg border border-slate-800">
              <span className="font-semibold text-amber-300 block mb-1">Trecho Evidência Literal:</span>
              <p className="text-amber-100 text-xs italic font-mono bg-slate-900 p-2 rounded border border-slate-800">
                "{c.evidencia}"
              </p>
            </div>
          )}

          {/* Transcrição Diarizada ou Completa */}
          <div>
            <span className="font-semibold text-slate-300 block mb-1">Transcrição Fonética Auditada:</span>
            {c.transcricao_diarizada?.length ? (
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2 max-h-60 overflow-y-auto leading-relaxed select-text font-sans">
                {c.transcricao_diarizada.map((t: any, i: number) => (
                  <div key={i} className="text-xs">
                    <span
                      className={`font-bold mr-1.5 ${
                        t.speaker === "CLIENTE"
                          ? "text-amber-400"
                          : t.speaker === "ATENDENTE"
                          ? "text-sky-400"
                          : "text-slate-400"
                      }`}
                    >
                      {t.speaker}:
                    </span>
                    <span className="text-slate-300">{t.text}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-300 font-mono text-xs max-h-60 overflow-y-auto leading-relaxed select-text">
                {c.transcricao || "[Áudio mudo ou sem fala identificada]"}
              </div>
            )}
          </div>

          {/* Reprocessar */}
          <div className="flex justify-end pt-2">
            <button onClick={handleReprocess} disabled={reprocessing} className="btn-ghost">
              <RefreshCw size={13} className={reprocessing ? "animate-spin" : ""} />
              {reprocessing ? "Processando..." : "Reauditar com OpenAI (ChatGPT)"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
