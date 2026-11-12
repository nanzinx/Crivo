import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

// ---------------------------------------------------------------- categorias
export const CATEGORIAS = [
  "EM_NEGOCIACAO",
  "NAO_E_O_CLIENTE",
  "SEM_INTERESSE",
  "LIGACAO_MUDA",
  "CAIXA_POSTAL",
  "INDETERMINADO",
] as const;

export const CAT_LABEL: Record<string, string> = {
  EM_NEGOCIACAO: "Em negociação",
  NAO_E_O_CLIENTE: "Não é o cliente",
  SEM_INTERESSE: "Sem interesse",
  LIGACAO_MUDA: "Ligação muda",
  CAIXA_POSTAL: "Caixa postal",
  INDETERMINADO: "Indeterminado",
  PENDENTE: "Pendente",
  MUDA_OU_CAIXA: "Muda ou caixa postal",
  NAO_TABULADO: "Não tabulado",
  OUTRO: "Outra tabulação",
};

export const catColor = (c?: string | null) => (c && CAT_LABEL[c] ? `var(--cat-${c}, var(--series-neutral))` : "var(--series-neutral)");
export const catLabel = (c?: string | null) => (c ? CAT_LABEL[c] ?? c : "Pendente");

export const STATUS_LABEL: Record<string, string> = {
  done: "Qualificada",
  pending: "Pendente",
  awaiting_ai: "Aguardando IA",
  error: "Erro",
};

export const DESLIG_LABEL: Record<string, string> = { CLIENTE: "Cliente", OPERADOR: "Operador", OUTRO: "Outro" };

// ---------------------------------------------------------------- formatação
const nf = new Intl.NumberFormat("pt-BR");
export const fmtInt = (n?: number | null) => (n == null ? "–" : nf.format(Math.round(n)));
export const fmtCompact = (n: number) =>
  new Intl.NumberFormat("pt-BR", { notation: n >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n);
export const fmtPct = (n?: number | null, d = 1) =>
  n == null ? "–" : `${n.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d })}%`;

/** Valores em dólar: centavos quando pequeno (US$ 0,0046), 2 casas quando grande. */
export const fmtUsd = (n?: number | null) => {
  if (n == null) return "–";
  const d = n !== 0 && Math.abs(n) < 0.1 ? 4 : 2;
  return `US$ ${n.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d })}`;
};

export const fmtDur = (s?: number | null) => {
  if (s == null || Number.isNaN(s)) return "–";
  const m = Math.floor(s / 60);
  const r = Math.round(s % 60);
  return m ? `${m}min ${String(r).padStart(2, "0")}s` : `${r}s`;
};
export const fmtClock = (s?: number | null) => {
  if (s == null || !Number.isFinite(s)) return "0:00";
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
};

export const fmtDateTime = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "–";
export const fmtDay = (iso: string) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" }).replace(".", "");
};

export const fmtAgo = (iso?: string | null) => {
  if (!iso) return "nunca";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "agora há pouco";
  if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
  return `há ${Math.floor(diff / 86400)} d`;
};

export const fmtPhone = (p?: string | null) => {
  if (!p) return "–";
  const d = p.replace(/\D/g, "");
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return p;
};

/** Mascara o telefone para exibição em listas (LGPD): (11) 9••••-1234 */
export const maskPhone = (p?: string | null) => {
  if (!p) return "–";
  const d = p.replace(/\D/g, "");
  if (d.length < 8) return p;
  return `(${d.slice(0, 2)}) ${d.slice(2, 3)}••••-${d.slice(-4)}`;
};

export const isoDate = (d: Date) => {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return z.toISOString().slice(0, 10);
};

export const initials = (name?: string | null) =>
  (name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
