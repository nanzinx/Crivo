"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  BellRing,
  CheckCircle2,
  ExternalLink,
  FileText,
  Hand,
  Mail,
  RefreshCw,
  Send,
  Webhook,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { useAuth } from "@/components/auth-context";
import { Button, Card, Empty, Pill, Skeleton } from "@/components/ui/primitives";
import { api, relatorioHtmlUrl, type Alerta, type Relatorio } from "@/lib/api";
import { cn, fmtAgo, fmtDateTime, fmtDay, fmtInt, fmtPct } from "@/lib/utils";

const DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"];
const descreverDias = (s: string) => {
  const m = s.match(/^(\d)-(\d)$/);
  return m ? `de ${DIAS[+m[1]]} a ${DIAS[+m[2]]}` : `nos dias ${s}`;
};

function lerNome() {
  try {
    return localStorage.getItem("crivo.revisor") ?? "";
  } catch {
    return "";
  }
}

export default function AlertasPage() {
  const qc = useQueryClient();
  const { data: al, isLoading } = useQuery({ queryKey: ["alertas"], queryFn: api.alertas, refetchInterval: 30_000 });
  const { data: rels } = useQuery({ queryKey: ["relatorios"], queryFn: api.relatorios });
  const tudo = () => qc.invalidateQueries();

  const avaliar = useMutation({
    mutationFn: api.avaliarAlertas,
    onSuccess: (r) => {
      toast.success(`${r.abertos} alerta(s) aberto(s)`, { description: `${r.novos} novo(s), ${r.resolvidos} resolvido(s), ${r.notificados} notificado(s)` });
      tudo();
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const testar = useMutation({
    mutationFn: api.testarNotificacao,
    onSuccess: (r) =>
      r.enviado
        ? toast.success(`Teste enviado por ${r.canais?.join(" e ")}`)
        : toast.error("Teste não enviado", { description: r.motivo ?? Object.values(r.erros ?? {}).join("; ") }),
    onError: (e) => toast.error((e as Error).message),
  });
  const gerar = useMutation({
    mutationFn: (enviar: boolean) => api.gerarRelatorio(enviar),
    onSuccess: (r) => {
      if (!r.envio) toast.success("Relatório de hoje gerado");
      else if (r.envio.enviado) toast.success(`Relatório gerado e enviado por ${r.envio.canais?.join(" e ")}`);
      else toast.warning("Relatório gerado, mas não enviado", { description: r.envio.motivo ?? Object.values(r.envio.erros ?? {}).join("; ") });
      tudo();
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const canais = al?.canais;
  const algumCanal = canais && (canais.webhook || canais.email);

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-2xl">
          <p className="mb-1 flex items-center gap-2 text-xs font-medium text-ink-muted">
            <BellRing className="h-3.5 w-3.5 text-brand" /> Monitoramento contínuo
          </p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Alertas e relatórios</h1>
          <p className="mt-2 text-sm text-ink-2">
            Os alertas são avaliados sozinhos a cada {al?.intervalo_minutos ?? 15} min e se resolvem quando a situação normaliza. O relatório do dia
            sai {al ? `às ${al.relatorio.hora}h, ${descreverDias(al.relatorio.dias)}` : "no fim do expediente"}.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => avaliar.mutate()} loading={avaliar.isPending}>
          <RefreshCw className="h-4 w-4" /> Avaliar agora
        </Button>
      </header>

      {isLoading || !al ? (
        <div className="space-y-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <>
          <section className="flex flex-col gap-2">
            {al.abertos.length === 0 ? (
              <div className="card flex items-center gap-3 border-good/30 bg-good/[.05] p-4">
                <span className="grid h-10 w-10 place-items-center rounded-2xl bg-good/15 text-good">
                  <CheckCircle2 className="h-5 w-5" />
                </span>
                <div>
                  <p className="text-sm font-semibold">Nenhum alerta aberto</p>
                  <p className="text-xs text-ink-muted">Operadores, troncos e pedidos de não ligar dentro do esperado.</p>
                </div>
              </div>
            ) : (
              <AnimatePresence initial={false}>
                {al.abertos.map((a, i) => (
                  <motion.div key={a.id} layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
                    <AlertaCard a={a} />
                  </motion.div>
                ))}
              </AnimatePresence>
            )}
          </section>

          <div className="grid gap-4 lg:grid-cols-5">
            <Card title="Relatório diário" subtitle="Resumo do dia para quem não abre o painel" className="lg:col-span-3">
              <div className="mb-4 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => gerar.mutate(false)} loading={gerar.isPending && !gerar.variables}>
                  <FileText className="h-4 w-4" /> Gerar o de hoje
                </Button>
                <Button size="sm" variant="primary" disabled={!algumCanal} onClick={() => gerar.mutate(true)} loading={gerar.isPending && gerar.variables === true}>
                  <Send className="h-4 w-4" /> Gerar e enviar agora
                </Button>
              </div>
              {!rels?.itens.length ? (
                <Empty icon={<FileText className="h-5 w-5" />} title="Nenhum relatório gerado ainda" />
              ) : (
                <ul className="divide-y divide-line">
                  {rels.itens.map((r) => (
                    <RelatorioLinha key={r.id} r={r} />
                  ))}
                </ul>
              )}
            </Card>

            <div className="flex flex-col gap-4 lg:col-span-2">
              <Card title="Para onde vão os avisos" subtitle="Configurado no .env do servidor">
                <ul className="space-y-2">
                  <Canal icon={<Webhook className="h-4 w-4" />} nome="Webhook (Slack, Teams, Google Chat)" ok={al.canais.webhook} variavel="NOTIFICAR_WEBHOOK_URL" />
                  <Canal icon={<Mail className="h-4 w-4" />} nome="E-mail" ok={al.canais.email} variavel="SMTP_HOST e NOTIFICAR_EMAILS" />
                </ul>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <p className="text-xs text-ink-muted">{algumCanal ? "Envie um teste para conferir." : "Sem canal: alertas e relatórios ficam só aqui no painel."}</p>
                  <Button size="sm" variant="soft" disabled={!algumCanal} onClick={() => testar.mutate()} loading={testar.isPending}>
                    <Send className="h-3.5 w-3.5" /> Testar
                  </Button>
                </div>
              </Card>
              <Card title="Regras" subtitle="Limites ajustáveis no .env (ALERTA_*)" delay={0.05}>
                <ul className="space-y-3">
                  {al.regras.map((r) => (
                    <li key={r.tipo}>
                      <p className="text-sm font-medium">{r.nome}</p>
                      <p className="text-xs text-ink-muted">{r.descricao}</p>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
          </div>

          <Card title="Resolvidos recentemente" subtitle="A condição normalizou e o alerta fechou sozinho">
            {al.recentes.length === 0 ? (
              <Empty title="Nenhum alerta resolvido ainda" />
            ) : (
              <ul className="divide-y divide-line">
                {al.recentes.map((a) => (
                  <li key={a.id} className="grid gap-1 py-2.5 text-sm sm:grid-cols-[1fr_auto] sm:items-center sm:gap-4">
                    <span className="flex min-w-0 items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-good" />
                      <span className="truncate">{a.titulo}</span>
                    </span>
                    <span className="num text-xs text-ink-muted">
                      aberto {fmtDateTime(a.aberto_em)} · resolvido {fmtAgo(a.resolvido_em)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function AlertaCard({ a }: { a: Alerta }) {
  const qc = useQueryClient();
  const { usuario, podeEditar } = useAuth();
  const crit = a.nivel === "critico";
  const Icon = crit ? AlertOctagon : AlertTriangle;
  const reconhecer = useMutation({
    mutationFn: () => {
      const nome = usuario?.nome || lerNome() || window.prompt("Seu nome (quem está cuidando deste alerta):") || "";
      if (!nome.trim()) throw new Error("Informe seu nome para assumir o alerta.");
      return api.reconhecerAlerta(a.id, nome);
    },
    onSuccess: () => {
      toast.success("Alerta assumido");
      qc.invalidateQueries({ queryKey: ["alertas"] });
    },
    onError: (e) => toast.error((e as Error).message),
  });
  return (
    <div className={cn("card flex flex-col gap-3 p-4 sm:flex-row sm:items-start", crit ? "border-critical/40 bg-critical/[.04]" : "border-warn/50 bg-warn/[.06]")}>
      <span className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-xl", crit ? "bg-critical/15 text-critical" : "bg-warn/20 text-ink")}>
        <Icon className="h-[18px] w-[18px]" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-semibold">
          {a.titulo} <Pill tone={crit ? "critical" : "warn"}>{crit ? "Crítico" : "Atenção"}</Pill>
        </p>
        <p className="mt-0.5 text-sm text-ink-2">{a.mensagem}</p>
        <p className="mt-1 text-[11px] text-ink-muted">
          Aberto {fmtAgo(a.aberto_em)} · atualizado {fmtAgo(a.atualizado_em)}
          {a.notificado_em ? ` · notificado ${fmtAgo(a.notificado_em)}` : ""}
          {a.reconhecido_por ? ` · com ${a.reconhecido_por}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 gap-2">
        {!a.reconhecido_por && podeEditar && (
          <Button size="sm" variant="ghost" onClick={() => reconhecer.mutate()} loading={reconhecer.isPending} title="Avisar que você está cuidando">
            <Hand className="h-3.5 w-3.5" /> Assumir
          </Button>
        )}
        {a.link && (
          <Link href={a.link}>
            <Button size="sm" variant="outline">
              Ver ligações <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </Link>
        )}
      </div>
    </div>
  );
}

function Canal({ icon, nome, ok, variavel }: { icon: React.ReactNode; nome: string; ok: boolean; variavel: string }) {
  return (
    <li className="flex items-center gap-3 rounded-xl border border-line p-2.5">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-raised text-ink-2">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm">{nome}</span>
        <span className="block truncate text-[11px] text-ink-muted">{ok ? "Configurado" : `Defina ${variavel}`}</span>
      </span>
      <Pill tone={ok ? "good" : "neutral"}>{ok ? "Ativo" : "Desligado"}</Pill>
    </li>
  );
}

function RelatorioLinha({ r }: { r: Relatorio }) {
  const qc = useQueryClient();
  const [aberto, setAberto] = useState(false);
  const d = r.dados;
  const reenviar = useMutation({
    mutationFn: () => api.enviarRelatorio(r.id),
    onSuccess: (x) => {
      x.envio?.enviado ? toast.success("Relatório enviado") : toast.error("Não enviado", { description: x.envio?.motivo ?? Object.values(x.envio?.erros ?? {}).join("; ") });
      qc.invalidateQueries({ queryKey: ["relatorios"] });
    },
  });
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <button onClick={() => setAberto((v) => !v)} className="text-sm font-medium hover:underline" aria-expanded={aberto}>
          {fmtDay(r.data)}
        </button>
        <span className="num text-xs text-ink-2">
          {fmtInt(d.total)} ligações · {fmtPct(d.divergencias.taxa)} divergência ({fmtInt(d.divergencias.por_gravidade.alta ?? 0)} alta){d.aguardando_avaliacao ? ` · ${fmtInt(d.aguardando_avaliacao)} aguardando avaliação` : ""}
        </span>
        <span className="ml-auto flex items-center gap-2">
          {r.enviado_em ? (
            <Pill tone="good">enviado {fmtAgo(r.enviado_em)}</Pill>
          ) : (
            <Pill tone={r.envio_detalhe ? "critical" : "neutral"}>{r.envio_detalhe ? "falhou" : "não enviado"}</Pill>
          )}
          <a href={relatorioHtmlUrl(r.id)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-medium text-brand-ink hover:underline">
            Ver e-mail <ExternalLink className="h-3 w-3" />
          </a>
        </span>
      </div>
      <AnimatePresence initial={false}>
        {aberto && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <pre className="mt-2 whitespace-pre-wrap rounded-xl bg-raised p-3 font-sans text-xs leading-relaxed text-ink-2">{r.texto}</pre>
            <Button size="sm" variant="ghost" className="mt-2" onClick={() => reenviar.mutate()} loading={reenviar.isPending}>
              <Send className="h-3.5 w-3.5" /> Enviar de novo
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}
