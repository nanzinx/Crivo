# Supervisor Argus

Escuta e qualifica ligações da discadora Argus (categorias/subcategorias) e alimenta um dashboard com filtros por data.

## Rodar

```powershell
# Backend (http://127.0.0.1:8000, docs em /docs)
cd backend
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
copy ..\.env.example ..\.env   # preencha ARGUS_TOKEN, ARGUS_CAMPAIGN_IDS, OPENAI_API_KEY
.venv\Scripts\python -m uvicorn app.main:app --port 8000

# Frontend (http://localhost:3000)
cd frontend; npm install; npm run dev
```

No dashboard: **Importar acervo local** (pasta `Gravações` + CSV de escuta) → **Qualificar pendentes**.

## Fluxos

| Fluxo | Como |
|---|---|
| Tempo real | Configure no Argus o webhook **Tabulação** (idTipoWebhook=2) para `POST /api/v1/webhooks/argus` (opcional `?secret=`). Baixa o áudio (`/cmd/downloadgravacao`) e qualifica. |
| Fallback | A cada 5 min consulta `/report/ligacoesdetalhadas` (últimos 15 min) das campanhas em `ARGUS_CAMPAIGN_IDS`. |
| Backfill | `POST /api/v1/sync/argus?data_inicio=2026-11-05&data_fim=2026-11-05` (janelas de 7 dias). |
| Acervo local | `POST /api/v1/sync/local` — parse do nome `YYYY-MM-DD_HHMMSS_nr{nr}_id{idLigacao}_{tel}_{nome}.mp3`. |

API: `GET /api/v1/calls` (filtros `data_inicio`, `data_fim`, `categoria`, `subcategoria`, `telefone`, `operador`, `campanha`, `q`, `status`), `/analytics/summary|timeline|operators`.

## Testes
`cd backend; .venv\Scripts\python -m pytest`
