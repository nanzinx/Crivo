<div align="center">

<img src="frontend/public/icon.svg" width="76" alt="Logo do Crivo" />

# Crivo

**Monitoria de qualidade das ligações: o que o operador tabulou × o que a monitora ouviu na gravação.**

Cruza os dados da discadora **Argus** com a avaliação da **monitoria de qualidade** sobre cada gravação para dar<br/>
uma visão clara do panorama das ligações, medir a qualidade da tabulação e acompanhar a operação.

<p>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" />
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.16x-009688?logo=fastapi&logoColor=white" />
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white" />
  <img alt="React" src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" />
  <img alt="Tailwind CSS" src="https://img.shields.io/badge/Tailwind-3-06B6D4?logo=tailwindcss&logoColor=white" />
  <img alt="CI" src="https://github.com/nanzinx/crivo/actions/workflows/ci.yml/badge.svg" />
  <img alt="Testes" src="https://img.shields.io/badge/testes-133%20passando-0ca30c" />
</p>

<a href="#-começando">Começando</a> ·
<a href="#-como-funciona">Como funciona</a> ·
<a href="#%EF%B8%8F-configuração">Configuração</a> ·
<a href="#%EF%B8%8F-modelo-de-tabulação">Modelo de tabulação</a> ·
<a href="#-monitoria-de-qualidade">Monitoria</a> ·
<a href="#-alertas-e-relatório-diário">Alertas</a> ·
<a href="#-api">API</a> ·
<a href="#%EF%B8%8F-roadmap">Roadmap</a>

<br/><br/>

<img src="docs/img/visao-geral.png" alt="Visão geral do Crivo" width="100%" />

<sub>Telas com <b>dados fictícios</b> gerados por <code>scripts/seed_demo.py</code>.</sub>

</div>

---

## ✨ O que o Crivo entrega

<table>
<tr>
<td width="50%" valign="top">

### 🎯 Matriz de contraste
Para cada tabulação feita no Argus, mostra como a monitoria avaliou a gravação. Células com **contorno vermelho** são divergências: o operador marcou uma coisa e a ligação foi outra.

</td>
<td width="50%" valign="top">

### 👥 Ranking de operadores
Taxa de divergência **sobre ligações avaliadas**, com faixas baixa/média/alta. Um clique filtra o painel inteiro pelo operador.

</td>
</tr>
<tr>
<td valign="top">

### 🎧 Escuta rápida
Player fixo com fila, velocidade de 1× a 2× e atalhos (`espaço`, `←` `→`, `Shift+←/→`). Na lista, `j`/`k` navega e `Enter` abre o detalhe para registrar o resultado.

</td>
<td valign="top">

### 🩺 Saúde do sistema
Último webhook, polling e downloads de gravação, com **alertas acionáveis** (webhook silencioso, token inválido, fila acumulada, erros). Upload do relatório da discadora com arrastar e soltar.

</td>
</tr>
<tr>
<td valign="top">

### 🔗 Links compartilháveis
Todos os filtros e a ligação aberta ficam na URL. Mande `…/ligacoes?operador=Ana&divergencia=true&ligacao=123` para alguém e a pessoa vê exatamente a mesma coisa.

</td>
<td valign="top">

### 📱 Responsivo e com tema
Funciona do celular ao monitor ultrawide. Tema claro, escuro ou do sistema. Paleta de categorias **validada para daltonismo**, e toda cor vem acompanhada de rótulo ou ícone.

</td>
</tr>
<tr>
<td valign="top">

### 🎧 Avaliação humana
Cada gravação baixada entra na **fila da monitoria**. A monitora ouve e registra o resultado (ou marca *não avaliável*, com o motivo). Só ligações avaliadas entram na divergência: o sistema nunca acusa o operador sem alguém ter ouvido.

</td>
<td valign="top">

### 👥 Perfis
A **monitora de qualidade** registra os resultados; o **supervisor** acompanha, confirma tabulações e cuida dos alertas; o perfil **só leitura** consulta. Cada avaliação fica no nome de quem avaliou.

</td>
</tr>
<tr>
<td valign="top">

### 🗂️ Modelo de tabulação
Cada tabulação do Argus entra num catálogo com um significado **sugerido**; a equipe confirma ou corrige na tela (ou por planilha), e as ligações são recalculadas na hora.

</td>
<td valign="top">

### 🚦 Gravidade e LGPD
Toda divergência tem gravidade **alta, média ou baixa**. O pedido de "não ligar mais" é marcado pela monitora e, se não for tabulado, vira divergência alta.

</td>
</tr>
<tr>
<td valign="top">

### 🔔 Alertas automáticos
Operador com muita divergência, pico de ligações mudas num tronco e pedido de "não ligar" sem registro. Os alertas abrem e se resolvem sozinhos e chegam por webhook (Slack, Teams, Google Chat) ou e-mail.

</td>
<td valign="top">

### 📨 Relatório diário
No fim do expediente, um resumo do dia: divergência por gravidade, operadores, mudas, LGPD e fila da monitoria, em texto e em e-mail HTML.

</td>
</tr>
</table>

<div align="center">
<img src="docs/img/modelo-tabulacao.png" alt="Modelo de tabulação" width="100%" />
<br/><br/>
<img src="docs/img/alertas.png" alt="Alertas e relatórios" width="100%" />
<br/><br/>
<img src="docs/img/matriz-operadores.png" alt="Matriz de contraste e ranking de operadores" width="100%" />
<br/><br/>
<img src="docs/img/ligacao-detalhe.png" alt="Detalhe de uma ligação divergente" width="49%" />
<img src="docs/img/visao-geral-escuro.png" alt="Tema escuro" width="49%" />
<br/>
<img src="docs/img/celular.png" alt="Versão para celular" width="23%" />
</div>

---

## 🧭 Como funciona

```mermaid
flowchart LR
    subgraph Argus["☎️ Discadora Argus"]
        WH[Webhook de tabulação]
        REP["/report/ligacoesdetalhadas"]
        REC[(Gravações)]
        CSV[Relatório detalhado CSV]
    end

    subgraph Backend["⚙️ Backend · FastAPI"]
        IN[Ingestão<br/>webhook · polling · backfill · pasta local]
        Q[[Download das gravações]]
        MON[Fila da monitoria<br/>avaliação humana]
        DIV[Divergência<br/>tabulação × monitoria]
        ID[Identidade<br/>é o cliente?]
        DB[(SQLite / PostgreSQL)]
        ST[Saúde<br/>eventos + alertas]
    end

    UI["🖥️ Frontend · Next.js"]

    WH --> IN
    REP --> IN
    CSV -->|upload ou pasta| DIV
    IN --> Q --> MON --> DIV --> ID --> DB
    REC -->|download| Q
    IN -.registra.-> ST
    Q -.registra.-> ST
    DB --> UI
    ST --> UI
```

1. **Ingestão.** A ligação chega pelo webhook de tabulação do Argus (tempo real). O polling a cada 5 min cobre webhooks perdidos, o backfill recupera períodos e a importação local lê o acervo de gravações.
2. **Gravação.** O áudio é baixado do Argus. Se o download falhar, a ligação fica com **erro** e pode ser baixada de novo pela tela.
3. **Avaliação.** A ligação entra na fila da monitoria (*Aguardando avaliação*). A monitora ouve e registra o resultado na [taxonomia oficial](#-taxonomia), marca se o cliente pediu para não ligar, ou indica que a ligação **não é avaliável** (áudio cortado, sem som...).
4. **Cruzamento.** O relatório detalhado da discadora traz operador, tronco, sinalização SIP e tabulação. O Crivo compara a tabulação do operador com o resultado da monitoria usando o [modelo de tabulação](#%EF%B8%8F-modelo-de-tabulação): **coerente** ou **divergente** (com gravidade). Ligações ainda não avaliadas não contam.
5. **Identidade.** Se alguém nega ser o titular mas o mesmo telefone e nome já se confirmaram antes, a ligação vira *"É o cliente (identificou-se em outras ligações)"*.
6. **Monitoramento.** Cada etapa registra sucesso ou falha. O painel de saúde transforma isso em alertas.

---

## 🚀 Começando

### Com Docker (recomendado para o servidor)

Sobe PostgreSQL, backend e frontend juntos:

```bash
cp .env.example .env
```

```bash
mkdir -p data && sudo chown -R 10001 data
```

```bash
docker compose up -d --build
```

- **Painel:** http://localhost:3000. No primeiro acesso, a tela pede para criar o administrador.
- **Webhook do Argus:** `http://<servidor>:8000/api/v1/webhooks/argus`.
- **Pasta `./data`:** guarda gravações, relatórios e downloads do Argus, e é montada dentro do container. O `chown` dá acesso de escrita ao usuário sem privilégios do container.
- **Senha do banco:** defina `POSTGRES_PASSWORD` no ambiente ou no `.env` antes de subir (o padrão é só para teste).
- **HTTPS:** coloque o painel atrás de um proxy com HTTPS e use `COOKIE_SEGURO=true`.

### Sem Docker (desenvolvimento)

### Pré-requisitos
- **Python 3.11+**
- **Node.js 20+**
- Opcional: token da **API Argus**. Sem eles o painel funciona com dados importados ou de demonstração.

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env         # Windows: copy ..\.env.example ..\.env
uvicorn app.main:app --reload --port 8000
```

A documentação interativa da API fica em **http://127.0.0.1:8000/docs**.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Abra **http://localhost:3000**. O Next repassa `/api/*` para o backend (variável `BACKEND_URL`, padrão `http://127.0.0.1:8000`), então não é preciso configurar CORS em desenvolvimento.

### 3. Dados de demonstração (opcional)

Para ver o painel funcionando sem dados reais (nenhum dado pessoal):

```bash
cd backend
python -m scripts.seed_demo            # cria ~600 ligações fictícias dos últimos 14 dias
python -m scripts.seed_demo --limpar   # remove só as ligações de demonstração
```

---

## ⚙️ Configuração

Tudo fica no arquivo **`.env` na raiz** do repositório (modelo em [`.env.example`](.env.example)). Caminhos relativos valem a partir da raiz.

| Variável | Para quê | Padrão |
|---|---|---|
| `ARGUS_TOKEN` | Header `Token-Signature` da API Argus | — |
| `ARGUS_CAMPAIGN_IDS` | Campanhas do polling/backfill (`12,15`) | — |
| `ARGUS_POLL_MINUTOS` | Intervalo do polling de segurança | `5` |
| `ARGUS_AUDIO_CHANNELS` | `1` mono · `2` estéreo · `3` pontas A/B separadas | `1` |
| `ARGUS_WEBHOOK_SECRET` | Segredo do webhook (`X-Webhook-Secret` ou `?secret=`) | — |
| `DATABASE_URL` | SQLite ou `postgresql+psycopg://…` | `sqlite:///./data/crivo.db` |
| `RECORDINGS_DIR` | Pasta com as gravações locais | `./data/gravacoes` |
| `ZIP_MAX_GRAVACOES` | Máximo de gravações num .zip exportado | `1000` |
| `CRUZAR_CSV` | Relatório detalhado da discadora | `./data/cruzar_dados.csv` |
| `LEGACY_CSV` / `LEGACY_HTML` | Escuta manual anterior | `./data/…` |
| `CORS_ORIGINS` | Origens liberadas no CORS | `http://localhost:3000,…` |
| `AUTH_ATIVO` | Exige login no painel e na API | `true` |
| `SESSAO_HORAS` | Duração da sessão | `12` |
| `COOKIE_SEGURO` | Cookie só por HTTPS (use `true` em produção com HTTPS) | `false` |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL do `docker compose` | — |
| `ALERTA_WEBHOOK_MINUTOS` | Silêncio de webhook que gera alerta | `30` |
| `HORARIO_COMERCIAL` | Janela dos alertas de webhook (seg–sáb) | `8-20` |

> [!IMPORTANT]
> **LGPD.** Gravações, avaliações e relatórios contêm dados pessoais.
> - A pasta `data/` e o `.env` estão no `.gitignore`: nunca versione esses arquivos.
> - Nas listas, o telefone aparece mascarado.
> - Com `AUTH_ATIVO=true` (padrão), todo acesso ao painel e à API exige login.

### Fontes de dados

| Fluxo | Como ativar |
|---|---|
| **Tempo real** | No Argus, configure o webhook **Tabulação** (`idTipoWebhook=2`) para `POST /api/v1/webhooks/argus`. A gravação é baixada e entra na fila da monitoria. |
| **Polling de segurança** | Defina `ARGUS_TOKEN` e `ARGUS_CAMPAIGN_IDS`. A cada `ARGUS_POLL_MINUTOS`, busca as ligações recentes. |
| **Recuperar período** | Tela *Saúde do sistema* → *Recuperar período*, ou `POST /api/v1/sync/argus?data_inicio=…&data_fim=…` (janelas de 7 dias). |
| **Acervo local** | Grave em `RECORDINGS_DIR` arquivos no padrão `YYYY-MM-DD_HHMMSS_nr{lead}_id{idLigacao}_{telefone}_{nome}.mp3` e clique em *Importar acervo local*. |
| **Relatório da discadora** | Arraste o CSV em *Saúde do sistema* → *Cruzar relatório da discadora*. O arquivo é lido **pelo nome das colunas**, em UTF-8 ou Windows-1252. |

---

## 🔐 Acesso

O painel exige login (`AUTH_ATIVO=true`, padrão).

**Primeiro acesso.** Com o banco vazio, a tela de login pede para criar o administrador. Depois, ele cadastra a equipe em *Usuários* (menu da conta).

| Perfil | Pode |
|---|---|
| **Administrador** | Tudo, inclusive gerenciar usuários e registrar o resultado das ligações |
| **Monitora de qualidade** | Ouvir as ligações e registrar o resultado, além do que o supervisor faz |
| **Supervisor** | Consultar **só as equipes vinculadas a ele**, dar ciência das avaliações, confirmar tabulações, importar, sincronizar e cuidar dos alertas |
| **Só leitura** | Apenas consultar |

**Como funciona:**
- **Senhas:** guardadas com scrypt e sal.
- **Sessão:** cookie `HttpOnly`, válido por `SESSAO_HORAS` (12). O banco guarda só o hash do token.
- **Bloqueio:** 5 senhas erradas seguidas bloqueiam o login por 5 minutos.
- **Assinatura das ações:** a avaliação das ligações e o "assumir alerta" ficam no nome de quem está logado.
- **Esqueceu a senha:** um administrador redefine em *Usuários*.

**Sem login:**
- O `/health` fica aberto, para monitoramento.
- O webhook do Argus é protegido só pelo `ARGUS_WEBHOOK_SECRET`.

**Scripts e integrações** podem usar o token devolvido por `POST /api/v1/auth/login` no cabeçalho `Authorization: Bearer <token>`.

> [!WARNING]
> `AUTH_ATIVO=false` desliga o login e todos entram como administrador. Use só no computador de desenvolvimento.

---

## 🗂️ Modelo de tabulação

A tabulação do Argus é texto livre e, muitas vezes, mais genérica que a taxonomia (ex.: "Muda / Caixa postal"). O modelo de tabulação diz, para cada tabulação, o que ela significa:

| Campo | Significado |
|---|---|
| **Tipo** | `resultado` (afirma o que aconteceu), `nao_tabulado` (ex.: tempo pós-atendimento: diverge se a monitoria ouviu conversa) ou `ignorar` (tabulação de sistema: nunca diverge) |
| **Categorias** | Os resultados da monitoria que **confirmam** a tabulação. Pode ser mais de uma |
| **Subcategoria** | Opcional. Se definida, subcategoria diferente vira divergência baixa |
| **Registra "não ligar"** | É a tabulação que o operador deve usar quando o cliente pede para não receber mais ligações |

**Como alimentar:**
- **Automático:** toda tabulação nova (webhook, polling, relatório da discadora) entra com um significado *sugerido* pelo texto, e o menu mostra quantas faltam confirmar. Quando o Argus envia o código da tabulação (`idTabulacao`), ele é guardado e passa a ter prioridade sobre o texto.
- **Pela tela:** *Modelo de tabulação* → confirmar ou corrigir. Ao salvar, as ligações daquela tabulação são recalculadas.
- **Por planilha:** exporte, edite e importe. Colunas: `tabulacao`, `tipo`, `categorias` (separadas por `|`, pelo nome ou pelo código), `subcategoria`, `nao_ligar` (sim/não) e, opcionalmente, `id_argus`.

> [!IMPORTANT]
> Enquanto uma tabulação estiver só *sugerida*, as divergências dela usam um palpite do sistema. A matriz e o detalhe da ligação avisam quando é o caso. Confirme as tabulações mais usadas primeiro.

### Gravidade da divergência

| Gravidade | Quando |
|---|---|
| 🔴 **Alta** | Envolve negociação (oportunidade perdida ou negociação que não existiu); houve conversa, mas foi tabulada como muda/caixa postal; ou o cliente pediu para não ligar e a tabulação não registra o pedido |
| 🟠 **Média** | Resultado de conversa trocado (ex.: "sem interesse" × "não é o cliente"); tabulou conversa e não houve; ou não tabulou uma conversa |
| ⚪ **Baixa** | Confusão entre muda e caixa postal, ou só a subcategoria diferente |

### Pedido de não ligar (LGPD)

A monitora marca quando quem atendeu **pede para não receber mais ligações** (recusa simples não conta). Isso vale para qualquer categoria e aparece com o selo *não ligar*, no filtro e na aba própria de "Para olhar agora".

O pedido só conta contra o operador se existir no Argus uma tabulação marcada como *Registra "não ligar"*. Sem ela, o operador não teria como registrar.

---

## 🎧 Monitoria de qualidade

Toda ligação com gravação entra na **fila da monitoria** (`/ligacoes?revisao=true`, ou o card *Aguardando avaliação* na visão geral). No detalhe da ligação, a monitora ouve e preenche o painel **Resultado da ligação**:
- categoria e subcategoria da [taxonomia](#-taxonomia);
- se quem atendeu pediu para não receber mais ligações;
- ou **Não dá para avaliar**, com o motivo (áudio cortado, sem som, gravação trocada...).

### Avaliação do script

Na **Monitoria** (fila de avaliação, com a meta do dia), *Avaliar* abre a tela de avaliação da ligação:

- **Player com linha do tempo.** Velocidade de 1× a 2×. Cada marcação vira um ponto colorido no áudio; clicar no ponto volta àquele momento.
- **Checklist do script** (o *Script de vendas*, transcrito do PDF). Cada trecho é marcado como **acertou**, **errou**, **divergência** (falou diferente) ou **não se aplica**. Errou e divergência pedem comentário.
- **Marcar agora.** Enquanto ouve, a monitora aperta *Acertou*, *Errou* ou *Diverg.* no momento em que o operador fala o trecho. O item é marcado e o momento fica gravado no áudio.
- **Desfecho.** *Venda* inclui a efetivação; *Recusa* inclui o tratamento da recusa; *Sem conversa* não pontua o script.
- **Nota em tempo real.** Soma dos pesos × valor (acertou 1, divergência 0,5, errou 0), dividida pelos pesos aplicáveis. *Não se aplica* e blocos fora do desfecho não contam. Errar um item **crítico** (documento, anuência, texto de confirmação) marca **falha crítica**, sem zerar a nota.
- **Resultado da ligação, observação e feedback** (pontos fortes e a melhorar). O feedback chega ao operador pelo supervisor.
- **Rascunho salvo sozinho e trava.** Só uma monitora avalia a ligação por vez. A trava vence em 15 minutos sem atividade.
- **Reabrir.** Pede o motivo e guarda no histórico como a avaliação estava antes.
- **Atalhos:** `espaço` toca/pausa, `←`/`→` 5 s, `j`/`k` muda de item, `1`–`4` marca o item, `m` cria um marcador.

O **Script de vendas** fica numa página própria, para consulta. O administrador cria uma nova versão, edita blocos, itens, pesos, itens críticos e o valor da divergência, e publica. A avaliação guarda a versão com que foi feita, então mudar o script não altera as notas antigas.

O resultado vira o resultado oficial da ligação e entra na comparação com a tabulação do operador na hora.

### Baixar as gravações (.zip)

Em **Ligações**, o botão **Baixar gravações (.zip)** junta as gravações da lista filtrada num único arquivo, pronto para mandar no BenHub. As pastas seguem esta ordem:

```
Equipe/Operador/Cliente/Tabulação/2026-11-20_170917_lig900000073.mp3
```

- Use os filtros da tela para escolher o que vai no arquivo: período, operador, resultado, só avaliadas etc.
- Junto vai `lista_gravacoes.csv`, com o caminho de cada arquivo e os dados da ligação. As ligações sem gravação no servidor aparecem nela marcadas.
- Limite de `ZIP_MAX_GRAVACOES` (1000) gravações por arquivo. Acima disso, filtre um período menor.
- Monitora, administrador e supervisor (só a própria equipe) podem baixar. O perfil só leitura, não.

### Supervisão

A página **Supervisão** mostra o levantamento da monitoria:
- nota média, % de avaliações com falha crítica e avaliações aguardando ciência;
- nota média por semana;
- trechos do script mais errados (e com divergência);
- operadores, da menor nota para a maior;
- a lista de avaliações com o feedback.

Ao abrir uma avaliação, o supervisor ouve os trechos marcados, lê as observações e o feedback e registra a **ciência**, com a devolutiva dada ao operador. O operador não acessa o sistema: o feedback chega a ele pelo supervisor. Se a monitora reabrir a avaliação, a ciência volta a ficar pendente (a anterior fica no histórico). Tudo exporta em CSV.

> [!IMPORTANT]
> **Cada supervisor vê só a própria equipe.** O administrador vincula as equipes (o grupo do Argus de cada ligação) em *Usuários → Equipes dos supervisores*. O filtro vale para tudo o que o supervisor acessa: ligações, áudio, painéis, exportações, avaliações e ciência. Supervisor sem equipe vinculada não vê nada. Admin, monitora e só leitura veem todas as equipes. A monitora pode **corrigir** uma avaliação; a ligação guarda quem avaliou e quando. Supervisores e o perfil só leitura veem o resultado, mas não registram.

| Status | Significado |
|---|---|
| Baixando gravação | Chegou do Argus; a gravação ainda não foi baixada |
| Aguardando avaliação | Gravação pronta, na fila da monitoria |
| Avaliada | A monitora registrou o resultado; conta na divergência |
| Não avaliável | A monitora não conseguiu avaliar; não conta na divergência |
| Erro | Falha no download; use *Baixar áudio de novo* |

> [!NOTE]
> **Versão anterior, com IA.** Ao atualizar um banco antigo, o Crivo migra sozinho: o que uma pessoa já tinha revisado vira avaliação, e o que só a IA tinha decidido volta para a fila. Os dados de IA (transcrições, custos) ficam ocultos no banco; para apagá-los de vez, faça um backup e rode `python -m scripts.limpar_dados_ia --sim` em `backend/`.

---

## 🔔 Alertas e relatório diário

A cada `ALERTA_INTERVALO_MINUTOS` (15), o backend avalia as regras abaixo. Um alerta fica **aberto** enquanto a condição durar e é **resolvido sozinho** quando ela some. A tela *Alertas e relatórios* mostra os abertos, o histórico e quem assumiu cada um.

| Regra | Quando abre (padrões) |
|---|---|
| Operador com divergência alta | 20%+ de divergência em 24h, com no mínimo 20 ligações avaliadas. **Crítico** com 5+ divergências de gravidade alta |
| Pico de mudas num tronco | 40%+ de ligações mudas em 3h (mínimo de 20) e 1,5× acima dos outros troncos. **Crítico** a partir de 70% |
| Pedido de não ligar sem registro | Qualquer caso nas últimas 24h (LGPD) |
| Falha crítica do sistema | Alertas críticos da tela Saúde do sistema (integração falhando, downloads parados) |

Todos os limites são ajustáveis no `.env` (`ALERTA_*`). A notificação sai quando o alerta abre ou piora para crítico, e não se repete antes de `ALERTA_RENOTIFICAR_HORAS` (6).

**Relatório diário:** gerado e enviado sozinho a partir de `RELATORIO_HORA` (19h), nos dias de `RELATORIO_DIAS` (`0-5` = segunda a sábado). Também pode ser gerado e enviado pela tela.

**Para onde vai.** Sem nenhum canal configurado, tudo fica só no painel. Os canais:

| Canal | Variáveis |
|---|---|
| Webhook (Slack, Microsoft Teams ou Google Chat) | `NOTIFICAR_WEBHOOK_URL` |
| E-mail (SMTP) | `SMTP_HOST`, `SMTP_PORTA`, `SMTP_USUARIO`, `SMTP_SENHA`, `SMTP_TLS`, `SMTP_REMETENTE`, `NOTIFICAR_EMAILS` |
| Links nas mensagens | `PAINEL_URL` (ex.: `http://crivo.empresa:3000`) |

Use o botão **Testar** da tela para conferir o envio.

> [!CAUTION]
> A URL do webhook e a senha do SMTP são credenciais: ficam só no `.env` do servidor, nunca no repositório.

## 🔌 API

<details>
<summary><b>Ver endpoints</b></summary>

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/v1/calls` | Lista paginada (filtros abaixo + `page`, `page_size`) |
| `GET` | `/api/v1/calls/{id}` | Detalhe com a avaliação da monitoria |
| `GET` | `/api/v1/calls/{id}/audio` | Áudio da gravação |
| `GET` | `/api/v1/calls/export` | CSV pronto para Excel (`;` + BOM) |
| `GET` | `/api/v1/calls/gravacoes.zip` | Gravações filtradas (ou `ids=`) num .zip: Equipe / Operador / Cliente / Tabulação |
| `GET` | `/api/v1/analytics/summary` | KPIs, categorias, matriz de contraste, ranking, distribuições |
| `GET` | `/api/v1/analytics/timeline` | Volume diário por categoria |
| `GET` | `/api/v1/analytics/horas` | Hora do dia × categoria |
| `GET` | `/api/v1/analyst/filters-options` | Opções reais de filtro (vindas do banco) |
| `GET` | `/api/v1/taxonomy` | Taxonomia oficial |
| `GET` | `/api/v1/saude` | Integrações, fila, erros recentes e alertas |
| `POST` | `/api/v1/webhooks/argus` | Recebe webhooks do Argus |
| `POST` | `/api/v1/sync/local` | Importa o acervo local e cruza com a discadora |
| `POST` | `/api/v1/sync/cruzar` | Cruza o relatório da discadora (upload `multipart` ou `CRUZAR_CSV`) |
| `POST` | `/api/v1/sync/argus` | Polling/backfill manual |
| `POST` | `/api/v1/sync/process` | Baixa as gravações pendentes ou com erro |
| `POST` | `/api/v1/sync/reprocess/{id}` | Baixa a gravação de uma ligação de novo |
| `GET` | `/api/v1/tabulacoes` | Modelo de tabulação com uso e divergência por tabulação |
| `PUT` | `/api/v1/tabulacoes/{id}` | Confirma/corrige uma tabulação e recalcula as ligações |
| `GET` | `/api/v1/tabulacoes/exportar` | Modelo em CSV |
| `POST` | `/api/v1/tabulacoes/importar` | Importa o modelo de uma planilha CSV |
| `POST` | `/api/v1/calls/{id}/resultado` | Registro rápido do resultado da ligação: monitora ou administrador |
| `GET` | `/api/v1/avaliacoes/fila` | Fila da monitoria, com a meta do dia |
| `POST` | `/api/v1/calls/{id}/avaliacao` | Abre (ou retoma) a avaliação do script, com trava |
| `GET` / `PUT` | `/api/v1/avaliacoes/{id}` | Lê / salva o rascunho (itens, marcadores, desfecho, feedback) |
| `POST` | `/api/v1/avaliacoes/{id}/finalizar` · `/nao-avaliavel` · `/reabrir` | Conclui, marca como não avaliável, reabre com motivo |
| `DELETE` | `/api/v1/avaliacoes/{id}/trava` | Libera a ligação para outra monitora |
| `GET` | `/api/v1/scripts/ativo` · `/api/v1/scripts/versoes` | Script em uso e versões |
| `POST` / `PUT` | `/api/v1/scripts/versoes` · `/{id}` · `/{id}/publicar` | Nova versão, edição do rascunho e publicação (admin) |
| `GET` / `PUT` | `/api/v1/parametros` | Meta diária de avaliações (admin edita) |
| `GET` | `/api/v1/supervisao/resumo` · `/avaliacoes` · `/exportar` | Levantamento, lista e CSV das avaliações (só as equipes do supervisor) |
| `POST` | `/api/v1/avaliacoes/{id}/ciencia` | Supervisor registra a ciência e a devolutiva |
| `GET` / `PUT` | `/api/v1/equipes` · `/api/v1/usuarios/{id}/grupos` | Equipes conhecidas e vínculo dos supervisores (admin) |
| `GET` | `/api/v1/alertas` | Alertas abertos, resolvidos, regras e canais |
| `POST` | `/api/v1/alertas/avaliar` | Avalia as regras agora |
| `POST` | `/api/v1/alertas/{id}/reconhecer` | Marca quem está cuidando do alerta |
| `GET` / `POST` | `/api/v1/relatorios` · `/api/v1/relatorios/gerar?enviar=true` | Lista / gera (e envia) o relatório do dia |
| `GET` | `/api/v1/relatorios/{id}/html` | Versão de e-mail do relatório |
| `POST` | `/api/v1/notificacoes/teste` | Envia uma mensagem de teste pelos canais configurados |

**Filtros** (os mesmos em listagem, exportação e analytics, então cards, gráficos e tabela sempre batem): `data_inicio`, `data_fim`, `categoria`, `subcategoria`, `operador`, `tronco`, `campanha`, `telefone`, `tipo_agente`, `tipo_discagem`, `desligado_por`, `divergencia`, `gravidade`, `nao_ligar`, `revisao` (fila da monitoria), `revisado` (já avaliada), `status`, `q`. A listagem aceita `ordenar=gravidade`.

</details>

---

## 🏷️ Taxonomia

| Categoria | Subcategorias |
|---|---|
| 🔵 **Em negociação** | Proposta em andamento · Aceite verbal · Agendamento de retorno · Migração para WhatsApp |
| 🟠 **Não é o cliente** | É o cliente (histórico) · Engano direto · Terceiro/família · Chip novo · Titular falecido · Reclamação recorrente |
| 🟢 **Sem interesse** | Cliente revoltado · Cliente calmo · Já possui / sem margem · Já é cliente |
| 🟡 **Ligação muda** | Atendente solitário · Cliente solitário · Falha de comunicação · Mudo total · Desligou na abertura · Ligação caiu |
| 🩷 **Caixa postal** | URA da operadora · Pós-bip · Fax/modem · Número inexistente |
| ⚪ **Indeterminado** | Sem dados suficientes · Áudio inaudível |

Fonte única: [`backend/app/taxonomy.py`](backend/app/taxonomy.py). Esta é a **versão 2**; cada ligação guarda a versão com que foi avaliada. O pedido de "não ligar" é uma marcação à parte, não uma categoria.

---

## 🗂️ Estrutura

```
crivo/
├── backend/
│   ├── app/
│   │   ├── api/            # rotas: auth, calls, saude, sync, tabulacoes, monitoramento, webhooks
│   │   ├── services/       # argus_client, avaliacoes, pipeline, tabulacoes, alertas, relatorio, …
│   │   ├── models.py       # Call, Avaliacao, Tabulacao, Usuario, Alerta, …
│   │   ├── taxonomy.py     # categorias oficiais
│   │   └── worker.py       # fila em thread (trocar por RQ/Celery ao escalar)
│   ├── scripts/            # seed_demo, limpar_dados_ia
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/            # páginas: visão geral, ligações, tabulação, alertas, saúde, usuários
│       ├── components/     # gráficos, player, filtros, shell, ui
│       └── lib/            # cliente da API e utilitários
└── docs/img/               # capturas do README
```

## 🧪 Testes

```bash
cd backend && python -m pytest
```

Para rodar a mesma suíte num PostgreSQL (o banco indicado é zerado):

```bash
cd backend && TEST_DATABASE_URL=postgresql+psycopg://usuario:senha@localhost/crivo_teste python -m pytest
```

O CI (GitHub Actions) roda os testes em SQLite e PostgreSQL, o build do frontend e o build das imagens Docker a cada envio.

```bash
cd frontend && npm run lint && npm run build
```

---

## 🛣️ Roadmap

- [x] **Semana 1: dados confiáveis.**
  - O cruzamento com a discadora está ligado e lê pelo cabeçalho.
  - A importação não quebra com ligações que já vieram do Argus.
  - O polling registra as falhas, e foi criado o painel de saúde.
  - As métricas usam os mesmos filtros e as bases certas.
  - Novo frontend.
- [x] **Custo de IA, etapas 1 e 2** (versão com IA, substituída pela monitoria humana).
- [x] **Semana 2: modelo de tabulação.**
  - Catálogo de tabulações (por código do Argus ou texto), editável na tela e por planilha.
  - Taxonomia v2: desligou na abertura, ligação caiu, já é cliente; pedido de não ligar (LGPD).
  - Divergência por gravidade.
  - Pendente: confirmar as tabulações reais com a lista oficial do Argus.
- [x] **Semana 3: medir a IA** (versão com IA, substituída pela monitoria humana).
- [x] **Semana 4: escuta precisa e alertas.**
  - Áudio estéreo com as pontas A/B separadas (feito na etapa 2 de custo).
  - Alertas automáticos e relatório diário por webhook/e-mail.
- [x] **Segurança e operação.**
  - Login com perfis, bloqueio por tentativas e gestão de usuários.
  - PostgreSQL testado (suíte inteira) e `docker compose` com banco, backend e frontend.
  - CI no GitHub Actions.
- [ ] **Próximos.**
  - Política de retenção de áudio (LGPD).
  - Alembic, quando houver a primeira mudança de banco que não seja só "adicionar coluna" (hoje as colunas novas são criadas sozinhas, em SQLite e PostgreSQL).
  - Registro de auditoria de quem alterou o quê.
- [x] **Monitoria humana, fase 1.**
  - Sai a IA: o resultado da ligação vem da monitora de qualidade (perfil próprio).
  - Fila da monitoria, *não avaliável* com motivo, migração automática do banco antigo.
- [x] **Monitoria humana, fase 2.**
  - Script de vendas versionado (transcrito do PDF) e avaliação item a item com marcações no áudio, nota e falha crítica.
- [x] **Monitoria humana, fase 3.**
  - Supervisão por equipe (só a própria), levantamento, ciência com devolutiva e exportação.
- [ ] **Monitoria humana, próximas fases.**
  - Controle de ponto (atrasos, pausas, almoço) no lugar da planilha.
  - Painel integrado de monitoria, ponto e alertas.

<div align="center"><sub>Feito para enxergar o que cada ligação realmente foi.</sub></div>
