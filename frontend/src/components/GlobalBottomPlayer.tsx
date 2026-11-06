"use client";
import { formatTime, COLORS } from "@/lib/api";
import { Play, Pause, SkipBack, SkipForward, RotateCcw, RotateCw, FileText, X } from "lucide-react";

export default function GlobalBottomPlayer({
  call,
  isPlaying,
  currentTime,
  duration,
  speed,
  onTogglePlay,
  onSeek,
  onSeekRelative,
  onPrev,
  onNext,
  onSetSpeed,
  onOpenModal,
  onClose,
}: {
  call: any;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  speed: number;
  onTogglePlay: () => void;
  onSeek: (t: number) => void;
  onSeekRelative: (delta: number) => void;
  onPrev: () => void;
  onNext: () => void;
  onSetSpeed: (s: number) => void;
  onOpenModal: () => void;
  onClose: () => void;
}) {
  if (!call) return null;

  const pct = duration > 0 ? (currentTime / duration) * 100 : 0;
  const tronco = call.tronco ? call.tronco.split(" - ")[0] : "ARGUS";
  const catColor = COLORS[call.categoria] || "#64748b";

  return (
    <div className="fixed bottom-0 inset-x-0 bg-slate-950/95 backdrop-blur-md border-t border-slate-800 shadow-2xl z-40 p-3 px-6 transition-all">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        
        {/* Info Chamada Atual */}
        <div className="flex items-center gap-3 w-full md:w-1/4 min-w-0">
          <div className="w-10 h-10 rounded-lg bg-indigo-600/20 text-indigo-400 flex items-center justify-center font-bold text-sm shrink-0 border border-indigo-500/30">
            {isPlaying ? (
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping" />
            ) : (
              <Play size={16} className="ml-0.5" />
            )}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] px-1.5 py-0.2 rounded font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                {tronco}
              </span>
              <span
                className="text-[10px] px-1.5 py-0.2 rounded font-semibold"
                style={{ background: catColor + "22", color: catColor }}
              >
                {call.categoria_label || call.categoria}
              </span>
            </div>
            <div className="text-xs font-bold text-white truncate mt-0.5">
              {call.nome_esperado || "Cliente Não Identificado"}
            </div>
            <div className="text-[10px] text-slate-400 truncate font-mono">
              {call.telefone || call.nome_arquivo}
            </div>
          </div>
        </div>

        {/* Controles Centrais + Barra de Progresso */}
        <div className="flex flex-col items-center gap-1.5 w-full md:w-2/4">
          <div className="flex items-center gap-3">
            <button
              onClick={onPrev}
              className="p-1.5 text-slate-400 hover:text-white transition"
              title="Chamada Anterior (P)"
            >
              <SkipBack size={16} />
            </button>
            <button
              onClick={() => onSeekRelative(-5)}
              className="p-1.5 text-slate-400 hover:text-white transition"
              title="Retroceder 5s (←)"
            >
              <RotateCcw size={16} />
            </button>

            <button
              onClick={onTogglePlay}
              className="w-9 h-9 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center shadow-lg transition transform hover:scale-105"
              title="Reproduzir / Pausar (Espaço)"
            >
              {isPlaying ? <Pause size={18} /> : <Play size={18} className="ml-0.5" />}
            </button>

            <button
              onClick={() => onSeekRelative(5)}
              className="p-1.5 text-slate-400 hover:text-white transition"
              title="Avançar 5s (→)"
            >
              <RotateCw size={16} />
            </button>
            <button
              onClick={onNext}
              className="p-1.5 text-slate-400 hover:text-white transition"
              title="Próxima Chamada (N)"
            >
              <SkipForward size={16} />
            </button>
          </div>

          <div className="flex items-center gap-2 w-full text-[11px] font-mono text-slate-400">
            <span className="w-10 text-right">{formatTime(currentTime)}</span>
            <input
              type="range"
              min={0}
              max={duration || 100}
              value={currentTime}
              step={0.1}
              onChange={(e) => onSeek(parseFloat(e.target.value))}
              className="w-full h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
            <span className="w-10">{formatTime(duration)}</span>
          </div>
        </div>

        {/* Lado Direito: Velocidade + Botão Ver Texto + Fechar */}
        <div className="flex items-center justify-end gap-2.5 w-full md:w-1/4">
          <div className="flex items-center bg-slate-900 rounded-lg p-0.5 border border-slate-800 text-[10px] font-bold">
            {[1.0, 1.25, 1.5, 2.0].map((s) => (
              <button
                key={s}
                onClick={() => onSetSpeed(s)}
                className={`px-1.5 py-0.5 rounded transition ${
                  speed === s
                    ? "text-indigo-400 bg-indigo-500/20"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {s}x
              </button>
            ))}
          </div>

          <button
            onClick={onOpenModal}
            className="px-2.5 py-1.5 text-xs font-semibold rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition flex items-center gap-1"
          >
            <FileText size={13} />
            <span>Ver Texto</span>
          </button>

          <button
            onClick={onClose}
            className="p-1 text-slate-500 hover:text-white transition"
            title="Fechar Player"
          >
            <X size={16} />
          </button>
        </div>

      </div>
    </div>
  );
}
