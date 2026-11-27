"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, AlertTriangle, ArrowRight, ClipboardCheck, Clock, Coffee, Eye, Gauge, UserCheck } from "lucide-react";
import Link from "next/link";
import { notaTone } from "@/components/avaliacao/calculo";
import { Skeleton } from "@/components/ui/primitives";
import { api, operadorUrl } from "@/lib/api";
import { cn, fmtDay, fmtInt } from "@/lib/utils";

/** "Painelzão": monitoria e ponto lado a lado, no topo da Visão geral (supervisor: só as equipes dele). */
export function PainelOperacao() {
  const { data, isLoading } = useQuery({ queryKey: ["painel"], queryFn: api.painel, refetchInterval: 60_000 });
  if (isLoading || !data) return <Skeleton className="h-36" />;
  const m = data.monitoria;
  const p = data.ponto;
  return (
    <section className="grid gap-3 lg:grid-cols-2">
      <div className="card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="card-title flex items-center gap-1.5">
            <ClipboardCheck className="h-4 w-4 text-ink-muted" /> Monitoria
          </h2>
          <Link href="/supervisao" className="inline-flex items-center gap-0.5 text-xs font-medium text-brand-ink hover:underline">
            Supervisão <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Mini href="/monitoria" icon={<ClipboardCheck className="h-3.5 w-3.5" />} label="Aguardando avaliação" valor={fmtInt(m.aguardando)} cls={m.aguardando ? "text-warn" : undefined} />
          <Mini icon={<UserCheck className="h-3.5 w-3.5" />} label="Avaliadas hoje" valor={fmtInt(m.avaliadas_hoje)} />
          <Mini
            href="/supervisao"
            icon={<Gauge className="h-3.5 w-3.5" />}
            label="Nota média (7 dias)"
            valor={m.nota_media_7d == null ? "–" : m.nota_media_7d.toLocaleString("pt-BR")}
            cls={notaTone(m.nota_media_7d)}
            sub={m.falhas_criticas_7d ? `${m.falhas_criticas_7d} com falha crítica` : undefined}
            subIcon={m.falhas_criticas_7d ? <AlertOctagon className="h-3 w-3 text-critical" /> : undefined}
          />
          <Mini href="/supervisao" icon={<Eye className="h-3.5 w-3.5" />} label="Sem ciência" valor={fmtInt(m.sem_ciencia)} cls={m.sem_ciencia ? "text-warn" : undefined} />
        </div>
      </div>
      <div className="card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="card-title flex items-center gap-1.5">
            <Clock className="h-4 w-4 text-ink-muted" /> Ponto {p && <span className="font-normal text-ink-muted">· {fmtDay(p.data)}</span>}
          </h2>
          <Link href="/ponto" className="inline-flex items-center gap-0.5 text-xs font-medium text-brand-ink hover:underline">
            Controle de ponto <ArrowRight className="h-3 w-3" />
          </Link>
        </div>
        {!p ? (
          <p className="text-sm text-ink-muted">Nenhum ponto importado ainda.</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Mini icon={<UserCheck className="h-3.5 w-3.5" />} label="Presentes" valor={fmtInt(p.presentes)} />
            <Mini icon={<AlertTriangle className="h-3.5 w-3.5" />} label="Atrasos" valor={fmtInt(p.atrasos)} cls={p.atrasos ? "text-critical" : undefined} />
            <Mini icon={<Coffee className="h-3.5 w-3.5" />} label="Almoço > 1h" valor={p.completo ? fmtInt(p.almoco_acima_1h ?? 0) : "–"} cls={p.almoco_acima_1h ? "text-warn" : undefined} />
            <div className="min-w-0 text-xs">
              <div className="text-ink-muted">Atrasados</div>
              {p.atrasados.length ? (
                <ul className="mt-1 space-y-0.5">
                  {p.atrasados.slice(0, 3).map((a) => (
                    <li key={a.operador} className="truncate">
                      <Link href={operadorUrl(a.operador)} className="hover:underline">
                        {a.operador.split(" ")[0]} <span className="num text-critical">{a.minutos}min</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="mt-1 text-ink-2">ninguém 🎉</div>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function Mini({ icon, label, valor, cls, sub, subIcon, href }: { icon: React.ReactNode; label: string; valor: string; cls?: string; sub?: string; subIcon?: React.ReactNode; href?: string }) {
  const corpo = (
    <>
      <div className="flex items-center gap-1 text-xs text-ink-muted">
        {icon} {label}
      </div>
      <div className={cn("num mt-0.5 text-xl font-semibold tracking-tight", cls)}>{valor}</div>
      {sub && (
        <div className="flex items-center gap-1 text-[11px] text-ink-muted">
          {subIcon} {sub}
        </div>
      )}
    </>
  );
  return href ? (
    <Link href={href} className="-m-1.5 min-w-0 rounded-xl p-1.5 transition hover:bg-raised">
      {corpo}
    </Link>
  ) : (
    <div className="min-w-0">{corpo}</div>
  );
}
