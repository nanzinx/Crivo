"use client";

import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { KeyRound, LogOut, Users } from "lucide-react";
import { useAuth } from "@/components/auth-context";
import { Activity, BellRing, LayoutDashboard, ListChecks, ListMusic, Moon, Sun, MonitorSmartphone } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState, type ReactNode } from "react";
import { PlayerBar } from "@/components/player/player-bar";
import { usePlayer } from "@/components/player/player-context";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Visão geral", short: "Visão", icon: LayoutDashboard },
  { href: "/ligacoes", label: "Ligações", short: "Ligações", icon: ListMusic },
  { href: "/tabulacoes", label: "Modelo de tabulação", short: "Tabulação", icon: ListChecks },
  { href: "/alertas", label: "Alertas e relatórios", short: "Alertas", icon: BellRing },
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

/** Portaria: sem sessão (com o login ligado), manda para /login; a tela de login não tem menu. */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { carregando, estado, usuario } = useAuth();
  const naLogin = pathname.startsWith("/login");
  const barrado = !carregando && !!estado?.auth_ativo && !usuario;
  useEffect(() => {
    if (barrado && !naLogin) router.replace(`/login?voltar=${encodeURIComponent(window.location.pathname + window.location.search)}`);
  }, [barrado, naLogin, router]);

  if (naLogin) return <>{children}</>;
  if (carregando || barrado) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <Logo className="h-10 w-10 animate-pulse" />
      </div>
    );
  }
  return <Chrome>{children}</Chrome>;
}

function UserMenu({ compacto }: { compacto?: boolean }) {
  const { usuario, estado, admin, sair } = useAuth();
  const [aberto, setAberto] = useState(false);
  const nome = usuario?.nome ?? "Acesso local";
  const iniciais = nome.split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("");
  return (
    <div className="relative">
      <button
        onClick={() => setAberto((v) => !v)}
        aria-expanded={aberto}
        aria-label="Menu da conta"
        className={cn("flex w-full items-center gap-2.5 rounded-xl text-left transition hover:bg-raised", compacto ? "p-1" : "px-2 py-1.5")}
      >
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand-soft text-[11px] font-bold text-brand-ink">{iniciais}</span>
        {!compacto && (
          <span className="min-w-0 leading-tight">
            <span className="block truncate text-sm font-medium">{nome}</span>
            <span className="block truncate text-[11px] text-ink-muted">{usuario?.papel_label ?? (estado?.auth_ativo === false ? "Login desligado" : "")}</span>
          </span>
        )}
      </button>
      <AnimatePresence>
        {aberto && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setAberto(false)} />
            <motion.div
              initial={{ opacity: 0, y: compacto ? -4 : 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className={cn(
                "card absolute z-50 w-56 p-1.5 text-sm shadow-pop",
                compacto ? "right-0 top-11" : "bottom-12 left-0",
              )}
              onClick={() => setAberto(false)}
            >
              {usuario && <div className="truncate px-2.5 py-1.5 text-xs text-ink-muted">{usuario.email}</div>}
              {usuario && (
                <Link href="/conta" className="flex items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-raised">
                  <KeyRound className="h-4 w-4 text-ink-muted" /> Trocar senha
                </Link>
              )}
              {admin && usuario && (
                <Link href="/usuarios" className="flex items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-raised">
                  <Users className="h-4 w-4 text-ink-muted" /> Usuários
                </Link>
              )}
              {usuario ? (
                <button onClick={() => sair()} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-critical hover:bg-critical/10">
                  <LogOut className="h-4 w-4" /> Sair
                </button>
              ) : (
                <p className="px-2.5 py-2 text-xs text-ink-muted">Login desligado (AUTH_ATIVO=false). Use só em desenvolvimento.</p>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

function Chrome({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { current } = usePlayer();
  const { data: saude } = useQuery({ queryKey: ["saude"], queryFn: api.saude, refetchInterval: 30_000 });
  const pendentes = saude?.tabulacoes_pendentes ?? 0;
  const { data: al } = useQuery({ queryKey: ["alertas"], queryFn: api.alertas, refetchInterval: 60_000 });
  const abertos = al?.abertos.length ?? 0;
  const criticos = al?.abertos.some((a) => a.nivel === "critico") ?? false;
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
              {href === "/alertas" && abertos > 0 && (
                <span
                  className={cn(
                    "relative ml-auto grid h-5 min-w-5 place-items-center rounded-full px-1.5 text-[10px] font-bold",
                    criticos ? "bg-critical text-white" : "bg-warn text-[#0b0b0b]",
                  )}
                  title={`${abertos} alerta(s) aberto(s)`}
                >
                  {abertos}
                </span>
              )}
              {href === "/tabulacoes" && pendentes > 0 && (
                <span className="relative ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-warn px-1.5 text-[10px] font-bold text-[#0b0b0b]" title={`${pendentes} tabulação(ões) para confirmar`}>
                  {pendentes}
                </span>
              )}
            </Link>
          ))}
        </nav>
        <div className="mt-auto space-y-3">
          <UserMenu />
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
          <UserMenu compacto />
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
      <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-6 border-t border-line bg-surface/90 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
        {NAV.map(({ href, short, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-ink-muted transition",
              isActive(href) && "text-ink",
            )}
          >
            <span className="relative">
              <Icon className={cn("h-5 w-5", isActive(href) && "text-brand")} />
              {href === "/tabulacoes" && pendentes > 0 && <span className="absolute -right-1 -top-0.5 h-2 w-2 rounded-full bg-warn" />}
              {href === "/alertas" && abertos > 0 && (
                <span className={cn("absolute -right-1 -top-0.5 h-2 w-2 rounded-full", criticos ? "bg-critical" : "bg-warn")} />
              )}
            </span>
            {short}
          </Link>
        ))}
      </nav>
    </div>
  );
}
