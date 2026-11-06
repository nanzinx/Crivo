"use client";

import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { Activity, LayoutDashboard, ListMusic, Moon, Sun, MonitorSmartphone } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState, type ReactNode } from "react";
import { PlayerBar } from "@/components/player/player-bar";
import { usePlayer } from "@/components/player/player-context";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Visão geral", short: "Visão", icon: LayoutDashboard },
  { href: "/ligacoes", label: "Ligações", short: "Ligações", icon: ListMusic },
  { href: "/saude", label: "Saúde do sistema", short: "Saúde", icon: Activity },
];

export function Logo({ className }: { className?: string }) {
  // Crivo = peneira: grade de furos que deixa passar só o que importa
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="9" fill="rgb(var(--ink))" />
      {[0, 1, 2].map((r) =>
        [0, 1, 2].map((c) => (
          <circle
            key={`${r}${c}`}
            cx={9.5 + c * 6.5}
            cy={9.5 + r * 6.5}
            r={r === 2 && c === 1 ? 2.6 : 1.9}
            fill={r === 2 && c === 1 ? "rgb(var(--brand))" : "rgb(var(--surface))"}
            opacity={r === 2 && c === 1 ? 1 : 0.85 - r * 0.2}
          />
        )),
      )}
    </svg>
  );
}

function ThemeToggle({ compact }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const opts = [
    { v: "light", icon: Sun, label: "Claro" },
    { v: "dark", icon: Moon, label: "Escuro" },
    { v: "system", icon: MonitorSmartphone, label: "Sistema" },
  ];
  if (compact) {
    const i = opts.findIndex((o) => o.v === theme);
    const cur = opts[i < 0 ? 2 : i];
    const Icon = cur.icon;
    return (
      <button
        onClick={() => setTheme(opts[(opts.indexOf(cur) + 1) % 3].v)}
        className="grid h-9 w-9 place-items-center rounded-xl text-ink-2 hover:bg-raised"
        aria-label={`Tema: ${cur.label}`}
      >
        {mounted && <Icon className="h-[18px] w-[18px]" />}
      </button>
    );
  }
  return (
    <div className="flex rounded-xl bg-raised p-1" role="radiogroup" aria-label="Tema">
      {opts.map(({ v, icon: Icon, label }) => (
        <button
          key={v}
          role="radio"
          aria-checked={mounted && theme === v}
          onClick={() => setTheme(v)}
          title={label}
          className={cn(
            "grid h-7 flex-1 place-items-center rounded-lg text-ink-muted transition",
            mounted && theme === v && "bg-surface text-ink shadow-sm",
          )}
        >
          <Icon className="h-4 w-4" />
        </button>
      ))}
    </div>
  );
}

function LiveBadge() {
  const { data } = useQuery({ queryKey: ["saude"], queryFn: api.saude, refetchInterval: 30_000 });
  const criticos = data?.alertas.filter((a) => a.nivel === "critico").length ?? 0;
  const atencao = data?.alertas.filter((a) => a.nivel === "atencao").length ?? 0;
  const tone = !data ? "bg-ink-muted" : criticos ? "bg-critical" : atencao ? "bg-warn" : "bg-good";
  const label = !data ? "Conectando…" : criticos ? `${criticos} crítico(s)` : atencao ? `${atencao} alerta(s)` : "Tudo certo";
  return (
    <Link href="/saude" className="flex items-center gap-2 rounded-xl px-2 py-1.5 text-xs text-ink-2 hover:bg-raised">
      <span className="relative flex h-2.5 w-2.5">
        <span className={cn("absolute inline-flex h-full w-full animate-pulse-ring rounded-full", tone)} />
        <span className={cn("relative inline-flex h-2.5 w-2.5 rounded-full", tone)} />
      </span>
      {label}
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { current } = usePlayer();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="min-h-dvh">
      {/* Sidebar (desktop) */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-line bg-surface/80 px-3 py-4 backdrop-blur lg:flex">
        <Link href="/" className="mb-6 flex items-center gap-2.5 px-2">
          <Logo className="h-8 w-8" />
          <div className="leading-tight">
            <div className="text-[15px] font-semibold tracking-tight">Crivo</div>
            <div className="text-[11px] text-ink-muted">Auditoria de ligações</div>
          </div>
        </Link>
        <nav className="flex flex-col gap-0.5">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "relative flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium text-ink-2 transition hover:text-ink",
                isActive(href) && "text-ink",
              )}
            >
              {isActive(href) && (
                <motion.span layoutId="nav-active" className="absolute inset-0 rounded-xl bg-raised" transition={{ type: "spring", stiffness: 500, damping: 40 }} />
              )}
              <Icon className="relative h-[18px] w-[18px]" />
              <span className="relative">{label}</span>
            </Link>
          ))}
        </nav>
        <div className="mt-auto space-y-3">
          <LiveBadge />
          <ThemeToggle />
        </div>
      </aside>

      {/* Topbar (mobile/tablet) */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-surface/85 px-4 backdrop-blur lg:hidden">
        <Link href="/" className="flex items-center gap-2">
          <Logo className="h-7 w-7" />
          <span className="font-semibold tracking-tight">Crivo</span>
        </Link>
        <div className="flex items-center gap-1">
          <LiveBadge />
          <ThemeToggle compact />
        </div>
      </header>

      <main className={cn("lg:pl-60", current ? "pb-40 lg:pb-28" : "pb-24 lg:pb-10")}>
        <AnimatePresence mode="wait">
          <motion.div
            key={pathname}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="mx-auto w-full max-w-[1440px] px-4 py-5 sm:px-6 lg:px-8 lg:py-8"
          >
            {children}
          </motion.div>
        </AnimatePresence>
      </main>

      <PlayerBar />

      {/* Bottom nav (mobile/tablet) */}
      <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-3 border-t border-line bg-surface/90 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
        {NAV.map(({ href, short, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-ink-muted transition",
              isActive(href) && "text-ink",
            )}
          >
            <Icon className={cn("h-5 w-5", isActive(href) && "text-brand")} />
            {short}
          </Link>
        ))}
      </nav>
    </div>
  );
}
