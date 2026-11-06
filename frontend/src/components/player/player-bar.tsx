"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Pause, Play, Rewind, FastForward, SkipBack, SkipForward, X } from "lucide-react";
import { CategoryBadge } from "@/components/ui/primitives";
import { cn, fmtClock } from "@/lib/utils";
import { usePlayer } from "./player-context";

const SPEEDS = [1, 1.25, 1.5, 2];

export function PlayerBar() {
  const p = usePlayer();
  const c = p.current;
  const pct = p.duration ? (p.time / p.duration) * 100 : 0;

  return (
    <AnimatePresence>
      {c && (
        <motion.div
          initial={{ y: 120, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 120, opacity: 0 }}
          transition={{ type: "spring", stiffness: 380, damping: 34 }}
          className="fixed inset-x-2 bottom-[68px] z-40 sm:inset-x-4 lg:bottom-4 lg:left-[calc(15rem+1rem)]"
          role="region"
          aria-label="Player de gravação"
        >
          <div className="card mx-auto max-w-[1400px] overflow-hidden border-line bg-surface/95 shadow-pop backdrop-blur">
            {/* barra de progresso clicável */}
            <input
              type="range"
              min={0}
              max={p.duration || 0}
              step={0.1}
              value={p.time}
              onChange={(e) => p.seek(Number(e.target.value))}
              aria-label="Posição da gravação"
              className="block h-1.5 w-full cursor-pointer appearance-none bg-raised accent-[rgb(var(--brand))]"
              style={{ background: `linear-gradient(to right, rgb(var(--brand)) ${pct}%, rgb(var(--raised)) ${pct}%)` }}
            />
            <div className="flex items-center gap-2 px-3 py-2.5 sm:gap-4 sm:px-4">
              <div className="flex items-center gap-0.5">
                <IconBtn onClick={p.prev} label="Anterior (Shift+←)" className="hidden sm:grid">
                  <SkipBack className="h-4 w-4" />
                </IconBtn>
                <IconBtn onClick={() => p.skip(-5)} label="Voltar 5s (←)">
                  <Rewind className="h-4 w-4" />
                </IconBtn>
                <button
                  onClick={p.toggle}
                  aria-label={p.playing ? "Pausar (espaço)" : "Tocar (espaço)"}
                  className="grid h-10 w-10 place-items-center rounded-full bg-ink text-surface transition active:scale-95"
                >
                  {p.playing ? <Pause className="h-[18px] w-[18px]" /> : <Play className="ml-0.5 h-[18px] w-[18px]" />}
                </button>
                <IconBtn onClick={() => p.skip(5)} label="Avançar 5s (→)">
                  <FastForward className="h-4 w-4" />
                </IconBtn>
                <IconBtn onClick={p.next} label="Próxima (Shift+→)" className="hidden sm:grid">
                  <SkipForward className="h-4 w-4" />
                </IconBtn>
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="truncate text-sm font-medium">{c.cliente_identificado || c.nome_esperado || "Sem nome"}</span>
                  <span className="hidden truncate text-xs text-ink-muted sm:inline">· {c.operador_nome}</span>
                </div>
                <div className="flex items-center gap-3">
                  <CategoryBadge code={c.categoria} className="text-ink-2" />
                  <span className="num text-xs text-ink-muted">
                    {fmtClock(p.time)} / {fmtClock(p.duration)}
                  </span>
                </div>
              </div>

              <button
                onClick={() => p.setSpeed(SPEEDS[(SPEEDS.indexOf(p.speed) + 1) % SPEEDS.length])}
                className="num h-8 rounded-lg border border-line px-2 text-xs font-semibold text-ink-2 hover:bg-raised"
                aria-label="Velocidade"
              >
                {p.speed}×
              </button>
              <IconBtn onClick={p.close} label="Fechar player">
                <X className="h-4 w-4" />
              </IconBtn>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function IconBtn({ children, onClick, label, className }: { children: React.ReactNode; onClick: () => void; label: string; className?: string }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn("grid h-8 w-8 place-items-center rounded-lg text-ink-2 transition hover:bg-raised hover:text-ink", className)}
    >
      {children}
    </button>
  );
}
