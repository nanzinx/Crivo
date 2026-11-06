"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Call } from "@/lib/api";
import { audioUrl } from "@/lib/api";

type PlayerState = {
  current: Call | null;
  playing: boolean;
  time: number;
  duration: number;
  speed: number;
  queue: Call[];
  play: (c: Call, queue?: Call[]) => void;
  toggle: () => void;
  seek: (t: number) => void;
  skip: (delta: number) => void;
  next: () => void;
  prev: () => void;
  setSpeed: (s: number) => void;
  close: () => void;
};

const Ctx = createContext<PlayerState | null>(null);

export function PlayerProvider({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const [current, setCurrent] = useState<Call | null>(null);
  const [queue, setQueue] = useState<Call[]>([]);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeedState] = useState(1);
  const queueRef = useRef<Call[]>([]);
  const currentRef = useRef<Call | null>(null);
  queueRef.current = queue;
  currentRef.current = current;

  const load = useCallback((c: Call) => {
    const a = ref.current;
    if (!a) return;
    setCurrent(c);
    setTime(0);
    setDuration(c.duracao_segundos || 0);
    a.src = audioUrl(c.id);
    a.play().catch(() => setPlaying(false));
  }, []);

  const step = useCallback(
    (dir: 1 | -1) => {
      const q = queueRef.current.filter((c) => c.tem_audio);
      const i = q.findIndex((c) => c.id === currentRef.current?.id);
      const n = q[i + dir];
      if (n) load(n);
    },
    [load],
  );

  useEffect(() => {
    const a = new Audio();
    a.preload = "metadata";
    ref.current = a;
    const on = (e: string, fn: () => void) => a.addEventListener(e, fn);
    on("timeupdate", () => setTime(a.currentTime));
    on("loadedmetadata", () => Number.isFinite(a.duration) && setDuration(a.duration));
    on("play", () => setPlaying(true));
    on("pause", () => setPlaying(false));
    on("ended", () => step(1));
    return () => {
      a.pause();
      a.src = "";
    };
  }, [step]);

  const play = useCallback(
    (c: Call, q?: Call[]) => {
      if (q) setQueue(q);
      const a = ref.current;
      if (currentRef.current?.id === c.id && a) {
        if (a.paused) a.play().catch(() => {});
        else a.pause();
        return;
      }
      if (a) a.playbackRate = speed;
      load(c);
    },
    [load, speed],
  );

  const toggle = useCallback(() => {
    const a = ref.current;
    if (!a || !currentRef.current) return;
    if (a.paused) a.play().catch(() => {});
    else a.pause();
  }, []);

  const seek = useCallback((t: number) => {
    if (ref.current) ref.current.currentTime = t;
  }, []);

  const skip = useCallback((d: number) => {
    const a = ref.current;
    if (a) a.currentTime = Math.max(0, Math.min(a.duration || 0, a.currentTime + d));
  }, []);

  const setSpeed = useCallback((s: number) => {
    setSpeedState(s);
    if (ref.current) {
      ref.current.defaultPlaybackRate = s; // mantém a velocidade ao trocar de faixa
      ref.current.playbackRate = s;
    }
  }, []);

  const close = useCallback(() => {
    ref.current?.pause();
    setCurrent(null);
  }, []);

  // Atalhos: espaço = play/pause, ←/→ = ±5s, Shift+←/→ = anterior/próxima
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(t.tagName) || t.isContentEditable || !currentRef.current) return;
      if (e.code === "Space") {
        e.preventDefault();
        toggle();
      } else if (e.code === "ArrowLeft") (e.shiftKey ? step(-1) : skip(-5));
      else if (e.code === "ArrowRight") (e.shiftKey ? step(1) : skip(5));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, skip, step]);

  const value = useMemo<PlayerState>(
    () => ({
      current,
      playing,
      time,
      duration,
      speed,
      queue,
      play,
      toggle,
      seek,
      skip,
      next: () => step(1),
      prev: () => step(-1),
      setSpeed,
      close,
    }),
    [current, playing, time, duration, speed, queue, play, toggle, seek, skip, step, setSpeed, close],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePlayer() {
  const v = useContext(Ctx);
  if (!v) throw new Error("usePlayer fora do PlayerProvider");
  return v;
}
