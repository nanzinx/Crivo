// Mesma conta do backend (services/avaliacoes.calcular), para a nota andar em tempo real na tela.
import type { Aplicabilidade, Calculo, Desfecho, EstadoItem, MarcaItem, ScriptVersao } from "@/lib/api";

export const secaoAplica = (a: Aplicabilidade, d: Desfecho | null | undefined) =>
  d === "sem_conversa" ? false : a === "venda" ? d === "venda" : a === "recusa" ? d === "recusa" : true;

export function calcular(script: ScriptVersao, itens: Record<number, MarcaItem>, desfecho: Desfecho | null | undefined): Calculo {
  const valor: Record<string, number> = { acertou: 1, errou: 0, divergencia: script.valor_divergencia };
  let soma = 0;
  let pesos = 0;
  const pendentes: number[] = [];
  const semComentario: number[] = [];
  const criticos: number[] = [];
  const contagem: Record<EstadoItem, number> = { acertou: 0, errou: 0, divergencia: 0, nao_se_aplica: 0 };
  for (const s of script.secoes) {
    if (!secaoAplica(s.aplicabilidade, desfecho)) continue;
    for (const it of s.itens) {
      const m = itens[it.id];
      const e = m?.estado;
      if (!e) {
        pendentes.push(it.id);
        continue;
      }
      contagem[e] += 1;
      if ((e === "errou" || e === "divergencia") && !m.comentario?.trim()) semComentario.push(it.id);
      if (e === "nao_se_aplica") continue;
      soma += it.peso * valor[e];
      pesos += it.peso;
      if (e === "errou" && it.critico) criticos.push(it.id);
    }
  }
  return {
    nota: pesos ? Math.round((1000 * soma) / pesos) / 10 : null,
    falha_critica: criticos.length > 0,
    itens_criticos_errados: criticos,
    pendentes,
    sem_comentario: semComentario,
    contagem,
  };
}

export const notaTone = (n: number | null | undefined) =>
  n == null ? "text-ink-muted" : n >= 85 ? "text-good" : n >= 65 ? "text-warn" : "text-critical";

export const ESTADOS: { v: EstadoItem; label: string; curto: string; tecla: string; cls: string; ativo: string }[] = [
  { v: "acertou", label: "Acertou", curto: "✓", tecla: "1", cls: "hover:border-good/60 hover:text-good", ativo: "border-good bg-good/15 text-good" },
  { v: "errou", label: "Errou", curto: "✗", tecla: "2", cls: "hover:border-critical/60 hover:text-critical", ativo: "border-critical bg-critical/15 text-critical" },
  { v: "divergencia", label: "Divergência", curto: "≈", tecla: "3", cls: "hover:border-warn/70 hover:text-ink", ativo: "border-warn bg-warn/20 text-ink" },
  { v: "nao_se_aplica", label: "Não se aplica", curto: "—", tecla: "4", cls: "hover:border-ink/30 hover:text-ink", ativo: "border-ink/30 bg-raised text-ink" },
];

export const MARCA_COR: Record<string, string> = {
  acertou: "bg-good",
  errou: "bg-critical",
  divergencia: "bg-warn",
  nota: "bg-brand",
};
