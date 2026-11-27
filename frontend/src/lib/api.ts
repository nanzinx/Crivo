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
  revisao?: string; // "true" = fila de avaliação (status pendente_avaliacao)
  revisado?: string; // "true" = a monitora já deu o veredito (avaliada ou não avaliável)
  gravidade?: string; // alta | media | baixa
  nao_ligar?: string; // "true" | "false"
  status?: string;
  q?: string;
};

export type StatusLigacao = "pendente" | "pendente_avaliacao" | "em_avaliacao" | "avaliada" | "nao_avaliavel" | "erro";

export type Avaliacao = {
  id: number;
  status: "rascunho" | "finalizada" | "nao_avaliavel";
  origem: "tela" | "importada" | "migrada";
  monitora_id: number | null;
  monitora_nome: string | null;
  categoria: string | null;
  subcategoria: string | null;
  pediu_nao_ligar: boolean;
  nao_avaliavel_motivo: string | null;
  iniciada_em: string | null;
  finalizada_em: string | null;
};

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
  status: StatusLigacao | string;
  avaliada?: boolean;
  categoria?: string | null;
  categoria_label?: string | null;
  subcategoria?: string | null;
  subcategoria_label?: string | null;
  conflito_identidade?: boolean;
  divergencia_tabulacao?: boolean;
  divergencia_detalhe?: string | null;
  divergencia_gravidade?: "alta" | "media" | "baixa" | null;
  pediu_nao_ligar?: boolean;
  tabulacao_id?: number | null;
  tabulacao_confirmada?: boolean | null;
  avaliado_por?: string | null;
  avaliado_em?: string | null;
  ligacao_referencia_id?: number | null;
  tem_audio?: boolean;
  erro?: string | null;
  // só no detalhe
  avaliacao?: Avaliacao | null;
  nome_arquivo?: string | null;
  ligacao_referencia?: Call;
};

export type CallsPage = { total: number; page: number; page_size: number; items: Call[] };

export type Dist = { tipo: string; total: number; pct: number };

export type Summary = {
  total: number;
  qualificadas: number;
  avaliadas: number;
  nao_avaliadas: number;
  nao_avaliaveis: number;
  aguardando_avaliacao: number;
  status: Record<string, number>;
  duracao_media: number;
  duracao_total_horas: number;
  conflitos_identidade: number;
  desligamentos: Dist[];
  agentes: Dist[];
  discagens: Dist[];
  troncos: (Dist & { tronco: string })[];
  divergencias: { total: number; comparaveis: number; taxa: number; por_gravidade: Record<"alta" | "media" | "baixa", number> };
  nao_ligar: number;
  matriz_contraste: {
    tabulacao_operador: string;
    esperada: string;
    esperadas: string[];
    tipo: TipoTabulacao;
    confirmada: boolean;
    total: number;
    categorias: Record<string, number>;
  }[];
  ranking_operadores: { operador: string; total: number; qualificadas: number; avaliadas: number; divergencias: number; taxa_divergencia: number }[];
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

export type Saude = {
  gerado_em: string;
  integracoes: {
    argus: { configurado: boolean; campanhas: number[]; polling_minutos: number };
  };
  fila: { tamanho: number };
  status_ligacoes: Record<StatusLigacao, number>;
  recebidas_24h: number;
  ultima_ligacao_em: string | null;
  eventos: Record<string, Evento>;
  erros_recentes: { id: number; id_ligacao: number | null; data_ligacao: string | null; erro: string | null; operador_nome: string | null }[];
  aguardando_avaliacao: number;
  tabulacoes_pendentes: number;
  alertas: { nivel: "critico" | "atencao"; titulo: string; mensagem: string }[];
};

export type Alerta = {
  id: number;
  chave: string;
  tipo: "operador" | "tronco" | "nao_ligar" | "sistema";
  nivel: "critico" | "atencao";
  titulo: string;
  mensagem: string;
  link: string | null;
  valor: number | null;
  aberto_em: string;
  atualizado_em: string;
  resolvido_em: string | null;
  notificado_em: string | null;
  reconhecido_por: string | null;
  reconhecido_em: string | null;
};

export type AlertasResp = {
  abertos: Alerta[];
  recentes: Alerta[];
  canais: { webhook: boolean; email: boolean };
  regras: { tipo: string; nome: string; descricao: string }[];
  intervalo_minutos: number;
  relatorio: { hora: number; dias: string };
};

export type Relatorio = {
  id: number;
  data: string;
  gerado_em: string;
  enviado_em: string | null;
  envio_detalhe: string | null;
  texto: string;
  dados: {
    total: number;
    qualificadas: number;
    nao_avaliadas?: number;
    divergencias: { total: number; taxa: number; por_gravidade: Record<string, number> };
    mudas_pct: number;
    nao_ligar: number;
    aguardando_avaliacao?: number;
    avaliadas_no_dia?: number;
    operadores: { operador: string; qualificadas: number; divergencias: number; taxa_divergencia: number; altas: number }[];
    alertas_abertos: { nivel: string; titulo: string; mensagem: string }[];
  };
  envio?: { enviado: boolean; canais?: string[]; erros?: Record<string, string>; motivo?: string };
};

export type ResultadoIn = {
  categoria?: string | null;
  subcategoria?: string | null;
  pediu_nao_ligar?: boolean;
  nao_avaliavel?: boolean;
  motivo?: string | null;
};

export type TipoTabulacao = "resultado" | "nao_tabulado" | "ignorar";

export type RegraTabulacao = {
  tipo: TipoTabulacao;
  categorias: string[];
  subcategoria: string | null;
  nao_ligar: boolean;
};

export type Tabulacao = RegraTabulacao & {
  id: number;
  nome: string;
  id_argus: number | null;
  confirmada: boolean;
  atualizado_em: string | null;
  ligacoes: number;
  qualificadas: number;
  divergencias: number;
  divergencias_altas: number;
  taxa_divergencia: number;
};

export type TabulacoesResp = {
  itens: Tabulacao[];
  resumo: { total: number; confirmadas: number; pendentes: number; ligacoes_pendentes: number; nao_ligar_registrado: boolean };
  opcoes: {
    tipos: Record<TipoTabulacao, string>;
    categorias: Record<string, { label: string; subs: Record<string, string> }>;
    gravidades: Record<string, string>;
  };
};

async function enviarJson<T>(path: string, method: string, body: unknown): Promise<T> {
  const r = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  await verificar(r);
  return r.json();
}

export function qs(params: Record<string, unknown> = {}) {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

export type Usuario = {
  id: number;
  email: string;
  nome: string;
  papel: Papel;
  papel_label: string;
  ativo: boolean;
  criado_em?: string | null;
  ultimo_login_em?: string | null;
};

export type Papel = "admin" | "supervisor" | "monitora" | "leitura";

/** Quem registra o resultado das ligações (o backend confere de novo). */
export const podeAvaliar = (u?: Pick<Usuario, "papel"> | null) => !!u && (u.papel === "monitora" || u.papel === "admin");

export type EstadoAuth = { auth_ativo: boolean; precisa_configurar: boolean; usuario: Usuario | null };

/** Sessão expirou ou não existe: volta para o login, lembrando onde estava. */
function irParaLogin() {
  if (typeof window === "undefined" || window.location.pathname.startsWith("/login")) return;
  const voltar = window.location.pathname + window.location.search;
  window.location.href = `/login?voltar=${encodeURIComponent(voltar)}`;
}

async function verificar(r: Response) {
  if (r.status === 401) irParaLogin();
  if (!r.ok) throw new Error(await parseError(r));
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
  await verificar(r);
  return r.json();
}

export async function post<T>(path: string, params: Record<string, unknown> = {}, body?: BodyInit): Promise<T> {
  const r = await fetch(`${path}${qs(params)}`, { method: "POST", body });
  await verificar(r);
  return r.json();
}

/** Chamadas de login: não redirecionam no 401 (o erro é mostrado no formulário). */
async function authJson<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
  if (!r.ok) throw new Error(await parseError(r));
  return r.json();
}

export const api = {
  estadoAuth: async (): Promise<EstadoAuth> => {
    const r = await fetch("/api/v1/auth/estado", { cache: "no-store" });
    if (!r.ok) throw new Error(await parseError(r));
    return r.json();
  },
  login: (email: string, senha: string) => authJson<Usuario>("/api/v1/auth/login", { email, senha }),
  primeiroAcesso: (email: string, nome: string, senha: string) => authJson<Usuario>("/api/v1/auth/primeiro-acesso", { email, nome, senha }),
  logout: () => authJson<{ ok: boolean }>("/api/v1/auth/logout"),
  trocarSenha: (atual: string, nova: string) => authJson<{ ok: boolean }>("/api/v1/auth/senha", { atual, nova }),
  usuarios: () => get<Usuario[]>("/api/v1/usuarios"),
  criarUsuario: (u: { email: string; nome: string; papel: string; senha: string }) => enviarJson<Usuario>("/api/v1/usuarios", "POST", u),
  editarUsuario: (id: number, u: Partial<{ nome: string; papel: string; ativo: boolean; senha: string }>) =>
    enviarJson<Usuario>(`/api/v1/usuarios/${id}`, "PATCH", u),
  alertas: () => get<AlertasResp>("/api/v1/alertas"),
  avaliarAlertas: () => post<{ novos: number; resolvidos: number; abertos: number; notificados: number }>("/api/v1/alertas/avaliar"),
  reconhecerAlerta: (id: number, por: string) => enviarJson<Alerta>(`/api/v1/alertas/${id}/reconhecer`, "POST", { por }),
  relatorios: () => get<{ itens: Relatorio[]; canais: { webhook: boolean; email: boolean } }>("/api/v1/relatorios"),
  gerarRelatorio: (enviar: boolean, data?: string) => post<Relatorio>("/api/v1/relatorios/gerar", { enviar, data }),
  enviarRelatorio: (id: number) => post<Relatorio>(`/api/v1/relatorios/${id}/enviar`),
  testarNotificacao: () => post<{ enviado: boolean; canais?: string[]; erros?: Record<string, string>; motivo?: string }>("/api/v1/notificacoes/teste"),
  registrarResultado: (id: number, r: ResultadoIn) => enviarJson<Call>(`/api/v1/calls/${id}/resultado`, "POST", r),
  tabulacoes: () => get<TabulacoesResp>("/api/v1/tabulacoes"),
  salvarTabulacao: (id: number, regra: RegraTabulacao) =>
    enviarJson<{ tabulacao: Tabulacao; recalculadas: number; mudaram: number }>(`/api/v1/tabulacoes/${id}`, "PUT", regra),
  importarTabulacoes: (arquivo: File) => {
    const fd = new FormData();
    fd.append("arquivo", arquivo);
    return post<{ importadas: number; erros: string[]; recalculadas: number; mudaram: number }>("/api/v1/tabulacoes/importar", {}, fd);
  },
  summary: (f: Filters) => get<Summary>("/api/v1/analytics/summary", f),
  timeline: (f: Filters) => get<TimelineRow[]>("/api/v1/analytics/timeline", f),
  horas: (f: Filters) => get<HourRow[]>("/api/v1/analytics/horas", f),
  calls: (f: Filters, page: number, page_size = 50, ordenar?: "data" | "gravidade") =>
    get<CallsPage>("/api/v1/calls", { ...f, page, page_size, ordenar }),
  call: (id: number) => get<Call>(`/api/v1/calls/${id}`),
  taxonomy: () => get<Taxonomy>("/api/v1/taxonomy"),
  options: () => get<FilterOptions>("/api/v1/analyst/filters-options"),
  saude: () => get<Saude>("/api/v1/saude"),
  processarPendentes: () => post<{ enfileiradas: number }>("/api/v1/sync/process"),
  baixarAudioDeNovo: (id: number) => post<{ enfileirada: boolean }>(`/api/v1/sync/reprocess/${id}`),
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
export const relatorioHtmlUrl = (id: number) => `/api/v1/relatorios/${id}/html`;
export const exportTabulacoesUrl = "/api/v1/tabulacoes/exportar";
export const exportUrl = (f: Filters) => `/api/v1/calls/export${qs(f)}`;
