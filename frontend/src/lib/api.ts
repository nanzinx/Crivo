export const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type Filters = {
  data_inicio?: string;
  data_fim?: string;
  categoria?: string;
  subcategoria?: string;
  tronco?: string;
  operador?: string;
  tipo_agente?: string;
  tipo_discagem?: string;
  desligado_por?: string;
  divergencia?: boolean | string;
  q?: string;
  telefone?: string;
  page?: number;
  page_size?: number;
};

export type CallItem = {
  id: number;
  id_ligacao?: number;
  nr_lead?: number;
  id_campanha?: number;
  telefone?: string;
  nome_esperado?: string;
  cliente_identificado?: string;
  operador_id?: string;
  operador_nome?: string;
  tabulacao_operador?: string;
  tabulacao_normalizada?: string;
  tronco?: string;
  direcionado?: number;
  tipo_agente?: "COMERCIAL" | "DIGITAL" | string;
  tipo_discagem?: "ATIVO" | "URA" | string;
  desligado_por?: "CLIENTE" | "OPERADOR" | "OUTRO" | string;
  desligamento_detalhe?: string;
  grupo_origem?: string;
  tempo_reacao_operador?: number;
  data_ligacao?: string;
  duracao_segundos?: number;
  origem: string;
  status: string;
  categoria?: string;
  categoria_label?: string;
  subcategoria?: string;
  subcategoria_label?: string;
  confianca?: number;
  motor?: string;
  resumo?: string;
  evidencia?: string;
  transcricao?: string;
  transcricao_diarizada?: any[];
  sentimento_cliente?: string;
  conflito_identidade?: boolean;
  divergencia_tabulacao?: boolean;
  divergencia_detalhe?: string;
  ligacao_referencia_id?: number;
  tem_audio?: boolean;
  erro?: string;
};

export function qs(params: Record<string, any>) {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "" && v !== null) {
      u.set(k, String(v));
    }
  });
  return u.toString();
}

export async function get<T>(path: string, params: Record<string, any> = {}): Promise<T> {
  const r = await fetch(`${API}${path}?${qs(params)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export async function post<T>(path: string, params: Record<string, any> = {}): Promise<T> {
  const r = await fetch(`${API}${path}?${qs(params)}`, { method: "POST" });
  if (!r.ok) {
    let msg = "";
    try {
      const j = await r.json();
      msg = j.detail || JSON.stringify(j);
    } catch {
      msg = (await r.text()) || `${r.status}`;
    }
    throw new Error(msg);
  }
  return r.json();
}

export const exportCsvUrl = (filters: Filters) => `${API}/api/v1/calls/export?${qs(filters)}`;

export const COLORS: Record<string, string> = {
  EM_NEGOCIACAO: "#10b981", // emerald
  NAO_E_O_CLIENTE: "#a855f7", // purple
  SEM_INTERESSE: "#f43f5e", // rose
  LIGACAO_MUDA: "#f59e0b", // amber
  CAIXA_POSTAL: "#06b6d4", // cyan
  INDETERMINADO: "#64748b", // slate
};

export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleString("pt-BR") : "-");
export const fmtDur = (n?: number | null) =>
  n == null ? "-" : `${Math.floor(n / 60)}:${String(Math.round(n % 60)).padStart(2, "0")}`;

export function formatTime(seconds?: number | null) {
  if (seconds == null || isNaN(seconds)) return "00:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

const iso = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
export const presets = () => {
  const t = new Date(),
    y = new Date(Date.now() - 864e5),
    w = new Date(Date.now() - 6 * 864e5);
  return {
    Todas: ["", ""],
    "05/11 (Gravações)": ["2026-11-05", "2026-11-05"],
    Hoje: [iso(t), iso(t)],
    Ontem: [iso(y), iso(y)],
    "7 dias": [iso(w), iso(t)],
  } as Record<string, string[]>;
};
