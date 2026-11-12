// Cliente da API do Crivo. O Next repassa /api/* para o backend (ver next.config.js).

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
  divergencia?: string; // "true" | "false"
  revisao?: string; // "true" | "false"
  status?: string;
  q?: string;
};

export type Turno = { speaker: string; text: string; sentiment?: string | null };

export type Call = {
  id: number;
  id_ligacao?: number | null;
  nr_lead?: number | null;
  id_campanha?: number | null;
  telefone?: string | null;
  nome_esperado?: string | null;
  cliente_identificado?: string | null;
  operador_id?: string | null;
  operador_nome?: string | null;
  tabulacao_operador?: string | null;
  tabulacao_normalizada?: string | null;
  tronco?: string | null;
  tipo_agente?: string | null;
  tipo_discagem?: string | null;
  desligado_por?: string | null;
  desligamento_detalhe?: string | null;
  grupo_origem?: string | null;
  tempo_reacao_operador?: number | null;
  data_ligacao?: string | null;
  duracao_segundos?: number | null;
  origem: string;
  status: string;
  categoria?: string | null;
  categoria_label?: string | null;
  subcategoria?: string | null;
  subcategoria_label?: string | null;
  confianca?: number | null;
  motor?: string | null;
  resumo?: string | null;
  evidencia?: string | null;
  sentimento_cliente?: string | null;
  conflito_identidade?: boolean;
  divergencia_tabulacao?: boolean;
  divergencia_detalhe?: string | null;
  precisa_revisao?: boolean;
  revisao_motivo?: string | null;
  fala_segundos?: number | null;
  custo_usd?: number;
  ligacao_referencia_id?: number | null;
  tem_audio?: boolean;
  erro?: string | null;
  // só no detalhe
  transcricao?: string | null;
  transcricao_diarizada?: Turno[] | null;
  metricas_acusticas?: Record<string, unknown> | null;
  nome_arquivo?: string | null;
  ligacao_referencia?: Call;
};

export type CallsPage = { total: number; page: number; page_size: number; items: Call[] };

export type Dist = { tipo: string; total: number; pct: number };

export type Summary = {
  total: number;
  qualificadas: number;
  status: Record<string, number>;
  duracao_media: number;
  duracao_total_horas: number;
  confianca_media: number | null;
  conflitos_identidade: number;
  desligamentos: Dist[];
  agentes: Dist[];
  discagens: Dist[];
  troncos: (Dist & { tronco: string })[];
  divergencias: { total: number; comparaveis: number; taxa: number };
  revisao: number;
  sem_ia: number;
  custo_usd: number;
  matriz_contraste: { tabulacao_operador: string; esperada: string; total: number; categorias: Record<string, number> }[];
  ranking_operadores: { operador: string; total: number; qualificadas: number; divergencias: number; taxa_divergencia: number }[];
  categorias: {
    codigo: string;
    label: string;
    total: number;
    pct: number;
    subs: { codigo: string | null; label: string; total: number }[];
  }[];
};

export type TimelineRow = { data: string } & Record<string, number | string>;
export type HourRow = { hora: number } & Record<string, number>;

export type Taxonomy = Record<string, { label: string; desc: string; subs: Record<string, string> }>;

export type FilterOptions = {
  operadores: { nome: string; total: number }[];
  troncos: { nome: string; total: number }[];
  campanhas: { nome: number; total: number }[];
  tipos_agente: string[];
  tipos_discagem: string[];
  desligado_por: string[];
  categorias: { codigo: string; label: string }[];
};

export type Evento = {
  nome: string;
  ok: boolean;
  em: string;
  detalhe: string | null;
  ultimo_sucesso_em: string | null;
  ultima_falha_em: string | null;
};

export type Custos = {
  hoje_usd: number;
  mes_usd: number;
  ligacoes_com_ia_mes: number;
  custo_medio_usd: number;
  minutos_transcritos_mes: number;
  resolvidas_sem_ia_mes: number;
  teto_diario_usd: number;
  teto_pct: number | null;
  modelo_transcricao: string;
  modelo_classificacao: string;
  diarizacao: boolean;
  modelos_sem_preco: string[];
  serie: { data: string; usd: number }[];
};

export type Saude = {
  gerado_em: string;
  integracoes: {
    ia: { configurada: boolean; modelo: string; transcricao: string };
    argus: { configurado: boolean; campanhas: number[]; polling_minutos: number };
  };
  fila: { tamanho: number };
  status_ligacoes: { pending: number; awaiting_ai: number; done: number; error: number };
  recebidas_24h: number;
  ultima_ligacao_em: string | null;
  eventos: Record<string, Evento>;
  erros_recentes: { id: number; id_ligacao: number | null; data_ligacao: string | null; erro: string | null; operador_nome: string | null }[];
  custos: Custos;
  revisao_pendente: number;
  alertas: { nivel: "critico" | "atencao"; titulo: string; mensagem: string }[];
};

export function qs(params: Record<string, unknown> = {}) {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

async function parseError(r: Response) {
  try {
    const j = await r.json();
    return typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
  } catch {
    return `${r.status} ${r.statusText}`;
  }
}

export async function get<T>(path: string, params: Record<string, unknown> = {}): Promise<T> {
  const r = await fetch(`${path}${qs(params)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json();
}

export async function post<T>(path: string, params: Record<string, unknown> = {}, body?: BodyInit): Promise<T> {
  const r = await fetch(`${path}${qs(params)}`, { method: "POST", body });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json();
}

export const api = {
  summary: (f: Filters) => get<Summary>("/api/v1/analytics/summary", f),
  timeline: (f: Filters) => get<TimelineRow[]>("/api/v1/analytics/timeline", f),
  horas: (f: Filters) => get<HourRow[]>("/api/v1/analytics/horas", f),
  calls: (f: Filters, page: number, page_size = 50) => get<CallsPage>("/api/v1/calls", { ...f, page, page_size }),
  call: (id: number) => get<Call>(`/api/v1/calls/${id}`),
  taxonomy: () => get<Taxonomy>("/api/v1/taxonomy"),
  options: () => get<FilterOptions>("/api/v1/analyst/filters-options"),
  saude: () => get<Saude>("/api/v1/saude"),
  reprocessar: (id: number) => post<{ enfileirada: boolean }>(`/api/v1/sync/reprocess/${id}`),
  processarPendentes: () => post<{ enfileiradas: number }>("/api/v1/sync/process"),
  importarLocal: () => post<Record<string, unknown>>("/api/v1/sync/local"),
  sincronizarArgus: (p: { ultimos_minutos?: number; data_inicio?: string; data_fim?: string }) =>
    post<{ ok: boolean; ligacoes: number; enfileiradas: number }>("/api/v1/sync/argus", p),
  cruzar: (arquivo?: File) => {
    const fd = new FormData();
    if (arquivo) fd.append("arquivo", arquivo);
    return post<{ linhas_enriquecidas: number; divergencias_encontradas: number; sem_correspondencia?: number; aviso?: string }>(
      "/api/v1/sync/cruzar",
      {},
      fd,
    );
  },
};

export const audioUrl = (id: number) => `/api/v1/calls/${id}/audio`;
export const exportUrl = (f: Filters) => `/api/v1/calls/export${qs(f)}`;
