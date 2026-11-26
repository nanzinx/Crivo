# Plano — Crivo com monitoria humana (sem IA), avaliação de script, supervisão e controle de ponto

## Resumo de Roteamento
- **Otimizador usado:** subagente `opus@high` (o esforço da sessão era desconhecido, então não contou como "igual").
- **Planner/Execução provisório (Fase 1):** feature multi-arquivo → Planner `opus@high`, Execução `sonnet@high`.
- **Planner/Execução final (Fase 3):** perfil **arquitetura** → Planner `opus@high`, Execução `opus@high`, Fallback `sonnet@xhigh`.
- **Mudou após a otimização? Sim.** O prompt otimizado revelou escopo escondido:
  - um módulo novo inteiro (controle de ponto, com paridade contra as macros VBA da planilha);
  - mudança no ciclo de vida da ligação, da qual dependem divergência, alertas e relatório;
  - concorrência entre monitoras, versionamento do script e um novo perfil.
- **Quota:** não verificada (sem o bloco `[prompt-router quota]` nesta sessão). Foram seguidos os primários.

## Prompt Otimizado
### Objetivo
Reformular o Crivo para que a **monitora de qualidade** (humana) faça a validação das ligações que hoje a IA faz:
1. **Remover toda a IA** (transcrição, classificação, custo, página "Qualidade da IA"), mantendo as demais funcionalidades.
2. **Avaliação interativa de aderência ao script** BenConsig por ligação: cada item do script marcado como acertou / errou / divergência / não se aplica, com marcação de tempo no áudio e comentário; resultado da ligação, observação geral e feedback ao operador.
3. **Visão dos supervisores** com o levantamento: notas, itens mais errados, evolução, observações, feedbacks e registro de ciência.
4. **"Painelzão" de controle de ponto** substituindo a planilha `Controle_de_Ponto_-_Argus.xlsm`: importação dos 3 CSV do Argus, a mesma configuração e relatórios de ontem/hoje com atrasos, almoço, TMP e QTP.
5. **Alertas, relatório diário e painel por operador** integrando monitoria e ponto.

### Escopo & Contexto
- **Branch:** `monitoria-humana`, a partir de `seguranca-operacao`. Não mexer em `main`.
- **Stack mantida:** FastAPI + SQLAlchemy (SQLite/PostgreSQL), Next.js 15 / React 19 / Tailwind / React Query / framer-motion / recharts, Docker compose e CI.
- **Entrega em fases,** cada uma utilizável e testada sozinha.
- **Funcionalidades mantidas:**
  - ingestão do Argus (webhook, polling, backfill, pasta de gravações, CSV de escuta, cruzamento com a discadora);
  - player, filtros na URL e exportação CSV;
  - matriz tabulação × resultado, ranking de operadores, divergência por gravidade via modelo de tabulação, taxonomia v2;
  - pedido de "não ligar" (LGPD);
  - alertas com histórico e "assumir", relatório diário;
  - login e usuários.
- **Fontes:**
  - PDF do script → seed do script (o PDF é escaneado; os textos serão digitados à mão e revisados pela operação).
  - Planilha → regras (macros VBA), configuração inicial e fixture de paridade.
- **Suposições:**
  - **S1.** A monitora avalia ligações já ingeridas, só ouvindo (sem transcrição).
  - **S2.** A revisão humana e a fila com amostra viram a avaliação; a categoria só vem da avaliação finalizada.
  - **S3.** O aviso "tabulou muda mas tem conversa", que dependia do VAD, sai.
  - **S4.** O ponto é importado por upload manual dos 3 CSV, com reconhecimento automático.
  - **S5.** Operador do ponto ↔ operador das ligações casados por nome normalizado, com mapeamento manual dos não casados.
  - **S6.** Divergência vale 0,5 (configurável); "não se aplica" sai do denominador.

### Requisitos & Edge Cases
Ver o plano abaixo; os detalhes completos ficam por fase.

### Critérios de Verificação
- **Testes:** pytest verde em SQLite e PostgreSQL.
- **IA removida:** `grep` por openai/whisper/ai_qualifier/ia_uso/categoria_ia vazio.
- **Subida:** sobe via `docker compose` sem chave; a ligação que chega via webhook fica `pendente_avaliacao`.
- **Migração:** a migração do banco da branch anterior não perde dados.
- **Testes de avaliação:** nota, falha crítica, seções condicionais, comentário obrigatório, versão do script presa, trava de concorrência, reabertura com auditoria, integração com a divergência.
- **Permissões:** testes por perfil.
- **Ponto:** paridade contra as abas da planilha, mais os edge cases, idempotência e reconhecimento automático.
- **Alertas e relatório:** alertas novos e conteúdo do relatório diário.
- **Frontend:** build, lint e typecheck.
- **Navegação:** percorrer os três fluxos (monitora, supervisor, importação do ponto) com capturas.
- **CI:** verde.

## Plano de Execução & Verificação

### O que o código mudou no plano
- **Migração de dados:** `init_db` só cria tabelas e colunas, então é preciso um passo `migrar_dados()` idempotente, controlado pela tabela `schema_migracoes`.
- **Status "done":** `status == "done"` é a referência de "qualificada" em `calls.py`, `alertas.py` e `relatorio.py`, e passa a ser `avaliada`.
- **Permissões:** é preciso `exigir_papel(...)` e o perfil `monitora`.
- **Dependências:** a duração do áudio passa a vir do `mutagen`. Saem `openai`, `av` e `numpy`.
- **Lint quebrado:** `next lint` está obsoleto e sem eslint instalado; corrigir na Fase 1.
- **Regras das macros** (detalhadas no plano do planejador):
  - atraso pelo turno mais próximo, só acima da tolerância, com arredondamento;
  - entrada = menor horário, saída = maior;
  - pausas só de quem está na jornada, contadas no dia em que começam;
  - almoço: início e fim do almoço mais longo, tempo = soma de todos;
  - grupos e pausas novos entram com o padrão definido na VBA;
  - o relatório "Hoje" só traz entrada e atraso.

### Fase 1 — Remover a IA; resultado vem da monitora (M, ~20%)
- **Remove:**
  - `services/{ai_qualifier,custos,qualidade,audio_analyzer}.py`, `api/qualidade.py`;
  - os scripts `validar_vad` e `comparar_transcricao`;
  - os testes `test_custo.py` (26) e `test_qualidade.py` (12), com justificativa;
  - a tela `frontend/app/qualidade` e as imagens do README.
- **Novo:**
  - tabela `avaliacoes` (categoria, subcategoria, não ligar, não avaliável, origem `tela|importada|migrada`) e coluna `calls.avaliacao_id`;
  - status `pendente` → `pendente_avaliacao` → `em_avaliacao` → `avaliada` / `nao_avaliavel` / `erro`;
  - migração: `done` com revisão humana → `avaliada`; os demais → `pendente_avaliacao`.
- **Rotas:**
  - saem `/qualidade*`, `/sync/process` e `/calls/{id}/revisao`;
  - entra `POST /calls/{id}/resultado`.
- **Verificação:** pytest nos dois bancos, `grep` vazio, `test_migracao.py`, `docker compose` + webhook, typecheck/lint/build.

### Fase 2 — Script versionado e tela de avaliação (G, ~30%; dividir em 2a backend / 2b UI)
- **Dados:**
  - script: `script_versoes`, `script_secoes` (aplicabilidade `sempre|venda|recusa`), `script_itens` (peso, crítico);
  - avaliação: `avaliacao_itens` (estado e comentário), `avaliacao_marcas` (segundos no áudio), `avaliacao_eventos` (auditoria);
  - `parametros` (meta diária, amostra);
  - `avaliacoes` ganha resultado, observação, feedback (fortes / a melhorar), nota, falha crítica e trava.
- **Rotas:**
  - script: `/scripts/versoes`, `/scripts/ativo`;
  - avaliação: `/avaliacoes/fila`, `POST /calls/{id}/avaliacao` (rascunho + trava), `GET`/`PUT /avaliacoes/{id}` (autosave), `/finalizar`, `/nao-avaliavel`, `/reabrir`, `DELETE /trava`.
- **Nota:** Σ peso × valor (acertou 1, divergência 0,5, errou 0) ÷ Σ pesos aplicáveis. Falha crítica = item crítico errado.
- **Trava:** UPDATE condicional atômico, com expiração de 15 min renovada pelo autosave.
- **Telas:**
  - fila de avaliação, tela de avaliação (timeline com marcadores clicáveis, checklist lateral, atalho "marcar agora", nota em tempo real);
  - editor do script (admin).
- **Verificação:** testes de nota, crítico, condicionais, comentário obrigatório, versão, trava, reabertura, divergência e permissões; capturas do fluxo.

### Fase 3 — Visão do supervisor (M, ~15%)
- **Dados:** `avaliacao_ciencias` e `supervisor_grupos` (P2: só a própria equipe).
- **Escopo por equipe:** filtro aplicado em todas as consultas de supervisão; testes garantem que um supervisor não vê a equipe de outro.
- **Rotas:** `/supervisao/{resumo,itens,evolucao}`, `POST /avaliacoes/{id}/ciencia` e os exports CSV.
- **Telas:**
  - painel (nota média, % falha crítica, itens mais errados e divergentes, evolução semanal, lista);
  - detalhe somente leitura com marcadores que tocam o trecho.

### Fase 4 — Controle de ponto (G, ~25%)
- **Dados:** `ponto_importacoes`, `ponto_jornadas`, `ponto_pausas`, `ponto_grupos`, `ponto_pausas_config`, `operadores`, `operador_aliases`; seed vindo da aba Config.
- **Rotas:** `/ponto/importar` (vários arquivos, reconhecimento automático), `/ponto/importacoes`, `/ponto/relatorio?data=&modo=dia|hoje`, `/ponto/resumo`, export, `/ponto/config`, `/operadores/vinculos`.
- **Telas:** resumo, dia fechado, hoje, config, importar, vínculos de operadores.
- **Verificação:** paridade célula a célula com Relatório Ontem e Hoje (fixtures pseudonimizadas); edge cases (sem entrada, falta, pausa sem fim, almoço fracionado, entrada antecipada, turno da tarde, atraso = tolerância, meia-noite, SEM SUPERVISOR, duplicadas); idempotência.

### Fase 5 — Alertas, relatório diário e painel integrado (M, ~10%)
- **Alertas:** as regras atuais passam a usar `avaliada`. Novos: aderência baixa, falha crítica, atraso recorrente, almoço > 1h.
- **Relatório diário:** blocos de monitoria e ponto.
- **Painel:** "painelzão" na Visão geral e uma página por operador (ponto + monitoria + divergência).

### Riscos
- **Volume "não avaliado":** sem a categorização automática, os KPIs caem. Mitigação: meta diária, amostra por operador e cobertura em %.
- **Migração em produção:** backup antes, e a migração é idempotente e testada.
- **Paridade com a planilha:** a VBA tem arredondamento próprio; replicar a fórmula exata.
- **LGPD nas fixtures:** pseudonimizar os nomes reais.
- **Concorrência entre monitoras:** trava com expiração.
- **Casamento de nomes:** normalização mais a tela de vínculos.

### Decisões do usuário (respondidas em 26/11)
- **P1. Dados de IA antigos: manter ocultos.**
  - As colunas saem do código e da tela, mas continuam no banco.
  - O script opcional `scripts/limpar_dados_ia.py` fica disponível para apagar no futuro.
- **P2. Supervisor vê só a própria equipe.** Isso muda o plano:
  - Entra a tabela `supervisor_grupos` (supervisor ↔ grupos do Argus), editada pelo admin na tela Usuários.
  - Todas as consultas de supervisão filtram pelos grupos do supervisor: painel, avaliações, exportações, ciência e, na Fase 4, o ponto.
  - A permissão é validada também no backend. Supervisor sem grupo vinculado não vê nada e recebe um aviso.
  - O grupo da ligação vem de `calls.grupo_origem` (do cruzamento com a discadora); quando o ponto existir, o grupo do ponto completa.
  - Ligação sem grupo fica visível só para admin e monitora, numa lista "sem equipe".
- **P3. Operador não acessa o sistema.** O feedback chega pelo supervisor, que registra a ciência ou devolutiva.
- **P4. Pontuação: adotar o padrão.**
  - Pesos iguais por item.
  - Item crítico só sinaliza "falha crítica", sem zerar a nota.
  - Divergência vale 0,5.
  - "Não se aplica" e seções condicionais fora do caso saem do denominador.
  - Pesos, crítico e valor da divergência ficam editáveis no editor do script, para a operação ajustar depois.

### Estimativa
Total de testes esperado ≈ 158 − 38 + ~110 ≈ **230**.
