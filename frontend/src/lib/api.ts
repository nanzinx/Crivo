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
  script_versao_id: number | null;
  desfecho: Desfecho | null;
  nota: number | null;
  falha_critica: boolean;
  observacao: string | null;
  feedback_fortes: string | null;
  feedback_melhorar: string | null;
};

// ---------------------------------------------------------------- script e avaliação
export type Aplicabilidade = "sempre" | "venda" | "recusa";
export type Desfecho = "venda" | "recusa" | "outro" | "sem_conversa";
export type EstadoItem = "acertou" | "errou" | "divergencia" | "nao_se_aplica";
export type TipoMarca = "acertou" | "errou" | "divergencia" | "nota";

export type ScriptItem = { id: number; ordem: number; texto: string; orientacao: string | null; peso: number; critico: boolean };
export type ScriptSecao = {
  id: number;
  ordem: number;
  titulo: string;
  aplicabilidade: Aplicabilidade;
  aplicabilidade_label: string;
  orientacao: string | null;
  itens: ScriptItem[];
};
export type ScriptVersao = {
  id: number;
  nome: string;
  numero: number;
  status: "rascunho" | "ativa" | "arquivada";
  valor_divergencia: number;
  criado_em: string | null;
  criado_por: string | null;
  publicada_em: string | null;
  avaliacoes: number;
  secoes: ScriptSecao[];
};
export type ScriptVersaoResumo = Omit<ScriptVersao, "secoes" | "valor_divergencia">;
export type ScriptIn = {
  nome: string;
  valor_divergencia: number;
  secoes: { titulo: string; aplicabilidade: Aplicabilidade; orientacao?: string | null; itens: { texto: string; orientacao?: string | null; peso: number; critico: boolean }[] }[];
};

export type MarcaItem = { item_id: number; estado: EstadoItem | null; comentario: string | null };
export type Marca = { id?: number; item_id: number | null; segundos: number; tipo: TipoMarca; texto: string | null };
export type Calculo = {
  nota: number | null;
  falha_critica: boolean;
  itens_criticos_errados: number[];
  pendentes: number[];
  sem_comentario: number[];
  contagem: Record<EstadoItem, number>;
};
export type AvaliacaoCompleta = Avaliacao & {
  call_id: number;
  script: ScriptVersao | null;
  itens: MarcaItem[];
  marcas: Marca[];
  eventos: { em: string; usuario: string | null; acao: string; detalhe: Record<string, unknown> | null }[];
  calculo: Calculo | null;
  ciencia?: Ciencia | null;
  trava: { nome: string | null; ate: string | null; ativa: boolean; minha: boolean };
  desfechos: Record<Desfecho, string>;
};
export type RascunhoIn = Partial<{
  desfecho: Desfecho | null;
  categoria: string | null;
  subcategoria: string | null;
  pediu_nao_ligar: boolean;
  observacao: string | null;
  feedback_fortes: string | null;
  feedback_melhorar: string | null;
  itens: MarcaItem[];
  marcas: Marca[];
}>;
export type FilaItem = {
  id: number;
  id_ligacao: number | null;
  data_ligacao: string | null;
  duracao_segundos: number | null;
  operador_nome: string | null;
  tabulacao_operador: string | null;
  grupo: string | null;
  status: StatusLigacao;
  tem_audio: boolean;
  rascunho: { monitora: string | null; trava: string | null; minha: boolean } | null;
};
export type Ciencia = { por: string; em: string; devolutiva: string | null };
export type SupervisaoFiltros = { data_inicio?: string; data_fim?: string; grupo?: string; operador?: string };
export type SupervisaoResumo = {
  avaliacoes: number;
  nota_media: number | null;
  falhas_criticas: number;
  falha_critica_pct: number;
  sem_ciencia: number;
  operadores: { operador: string; grupo: string | null; avaliacoes: number; nota_media: number | null; falhas_criticas: number; sem_ciencia: number; ultima: string | null }[];
  evolucao: { semana: string; avaliacoes: number; nota_media: number | null; falhas_criticas: number }[];
  itens: { texto: string; secao: string; critico: boolean; avaliados: number; acertou: number; errou: number; divergencia: number; erro_pct: number; divergencia_pct: number }[];
  escopo: { restrito: boolean; grupos: string[] | null };
};
export type SupervisaoLinha = {
  id: number;
  call_id: number;
  id_ligacao: number | null;
  data_ligacao: string | null;
  operador_nome: string | null;
  grupo: string | null;
  tabulacao_operador: string | null;
  monitora_nome: string | null;
  finalizada_em: string | null;
  nota: number | null;
  falha_critica: boolean;
  desfecho: Desfecho | null;
  categoria: string | null;
  divergencia_tabulacao: boolean;
  observacao: string | null;
  feedback_fortes: string | null;
  feedback_melhorar: string | null;
  ciencia: Ciencia | null;
};
export type Equipes = { grupos: { nome: string; ligacoes: number }[]; supervisores: { id: number; nome: string; ativo: boolean; grupos: string[] }[] };
export type PontoLinha = {
  operador: string;
  grupo: string | null;
  entrada_seg: number | null;
  saida_seg: number | null;
  jornada_seg: number | null;
  almoco_inicio: string | null;
  almoco_fim: string | null;
  almoco_seg: number | null;
  tmp_seg: number | null;
  qtp: number | null;
  atraso_min: number;
  observacao: string | null;
};
export type PontoRelatorio = {
  data: string;
  modo: "completo" | "entrada";
  resumo: { operadores: number; presentes: number; atrasos: number; almoco_medio_seg: number | null; almoco_acima_1h: number | null; tmp_medio_seg: number | null };
  linhas: PontoLinha[];
};
export type PontoConfig = {
  grupos: { grupo: string; incluir: boolean; entrada_prevista: string; tolerancia_min: number; operadores: number }[];
  pausas: { descricao: string; conta: boolean }[];
  almoco: string;
  ignorar: string;
};
export type PontoImportado = { arquivo: string; tipo: "ponto" | "pausas" | null; data: string | null; linhas: number; erro: string | null; substituiu: boolean };
export type Fila = { total: number; page: number; page_size: number; itens: FilaItem[]; meta: { diaria: number; feitas_hoje: number } };

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
  grupos?: { nome: string; total: number }[];
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
    if (typeof j.detail === "string") return j.detail;
    if (j.detail?.problemas) return [j.detail.mensagem, ...j.detail.problemas].filter(Boolean).join("\n");
    if (Array.isArray(j.detail)) return j.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("\n");
    return JSON.stringify(j.detail ?? j);
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
  scriptAtivo: () => get<ScriptVersao>("/api/v1/scripts/ativo"),
  scriptVersoes: () => get<ScriptVersaoResumo[]>("/api/v1/scripts/versoes"),
  scriptVersao: (id: number) => get<ScriptVersao>(`/api/v1/scripts/versoes/${id}`),
  novoRascunhoScript: () => post<ScriptVersao>("/api/v1/scripts/versoes"),
  salvarScript: (id: number, s: ScriptIn) => enviarJson<ScriptVersao>(`/api/v1/scripts/versoes/${id}`, "PUT", s),
  publicarScript: (id: number) => post<ScriptVersao>(`/api/v1/scripts/versoes/${id}/publicar`),
  descartarScript: (id: number) => enviarJson<{ ok: boolean }>(`/api/v1/scripts/versoes/${id}`, "DELETE", {}),
  parametros: () => get<Record<string, { descricao: string; valor: string }>>("/api/v1/parametros"),
  salvarParametros: (p: Record<string, string>) => enviarJson<Record<string, { descricao: string; valor: string }>>("/api/v1/parametros", "PUT", p),
  fila: (p: { operador?: string; page?: number }) => get<Fila>("/api/v1/avaliacoes/fila", p),
  iniciarAvaliacao: (callId: number) => post<AvaliacaoCompleta>(`/api/v1/calls/${callId}/avaliacao`),
  avaliacao: (id: number) => get<AvaliacaoCompleta>(`/api/v1/avaliacoes/${id}`),
  salvarAvaliacao: (id: number, r: RascunhoIn) => enviarJson<AvaliacaoCompleta>(`/api/v1/avaliacoes/${id}`, "PUT", r),
  finalizarAvaliacao: (id: number) => post<AvaliacaoCompleta>(`/api/v1/avaliacoes/${id}/finalizar`),
  naoAvaliavel: (id: number, motivo: string) => enviarJson<AvaliacaoCompleta>(`/api/v1/avaliacoes/${id}/nao-avaliavel`, "POST", { motivo }),
  reabrirAvaliacao: (id: number, motivo: string) => enviarJson<AvaliacaoCompleta>(`/api/v1/avaliacoes/${id}/reabrir`, "POST", { motivo }),
  liberarAvaliacao: (id: number, forcar = false) => enviarJson<{ ok: boolean }>(`/api/v1/avaliacoes/${id}/trava?forcar=${forcar}`, "DELETE", {}),
  supervisaoResumo: (f: SupervisaoFiltros) => get<SupervisaoResumo>("/api/v1/supervisao/resumo", f),
  supervisaoAvaliacoes: (f: SupervisaoFiltros & { ciencia?: string; falha_critica?: string; page?: number }) =>
    get<{ total: number; page: number; page_size: number; itens: SupervisaoLinha[] }>("/api/v1/supervisao/avaliacoes", f),
  darCiencia: (id: number, devolutiva: string) => enviarJson<Ciencia>(`/api/v1/avaliacoes/${id}/ciencia`, "POST", { devolutiva }),
  equipes: () => get<Equipes>("/api/v1/equipes"),
  definirGrupos: (uid: number, grupos: string[]) => enviarJson<{ id: number; grupos: string[] }>(`/api/v1/usuarios/${uid}/grupos`, "PUT", { grupos }),
  pontoDatas: () => get<{ data: string; tem_pausas: boolean }[]>("/api/v1/ponto/datas"),
  pontoRelatorio: (p: { data: string; modo: string; grupo?: string }) => get<PontoRelatorio>("/api/v1/ponto/relatorio", p),
  pontoImportacoes: () =>
    get<{ id: number; tipo: string; data: string; arquivo: string; linhas: number; importado_em: string; importado_por: string | null }[]>("/api/v1/ponto/importacoes"),
  pontoImportar: (arquivos: File[]) => {
    const fd = new FormData();
    arquivos.forEach((a) => fd.append("arquivos", a));
    return post<{ arquivos: PontoImportado[] }>("/api/v1/ponto/importar", {}, fd);
  },
  pontoConfig: () => get<PontoConfig>("/api/v1/ponto/config"),
  salvarPontoConfig: (c: Partial<Omit<PontoConfig, "grupos">> & { grupos?: Omit<PontoConfig["grupos"][number], "operadores">[] }) =>
    enviarJson<PontoConfig>("/api/v1/ponto/config", "PUT", c),
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
export const exportSupervisaoUrl = (f: SupervisaoFiltros) => `/api/v1/supervisao/exportar${qs(f)}`;
export const gravacoesZipUrl = (f: Filters) => `/api/v1/calls/gravacoes.zip${qs(f)}`;

/** Baixa o .zip das gravações filtradas. Devolve quantas entraram e quantas ficaram sem áudio. */
export async function baixarGravacoesZip(f: Filters) {
  const r = await fetch(gravacoesZipUrl(f), { cache: "no-store" });
  await verificar(r);
  const blob = await r.blob();
  const nome = /filename\*?=(?:UTF-8'')?"?([^";]+)/i.exec(r.headers.get("content-disposition") ?? "")?.[1] ?? "gravacoes.zip";
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: decodeURIComponent(nome) });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return { incluidas: Number(r.headers.get("x-gravacoes-incluidas") ?? 0), semAudio: Number(r.headers.get("x-gravacoes-sem-audio") ?? 0) };
}

export const pontoExportUrl = (p: { data: string; modo: string; grupo?: string }) => `/api/v1/ponto/exportar${qs(p)}`;
export const exportUrl = (f: Filters) => `/api/v1/calls/export${qs(f)}`;
