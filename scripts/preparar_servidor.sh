#!/usr/bin/env bash
# Prepara o .env do servidor para publicar o Crivo com HTTPS. Gera aqui mesmo as senhas e o segredo do
# webhook (nada disso passa por chat ou repositório) e mostra a URL para cadastrar no Argus.
#
# Uso: ./scripts/preparar_servidor.sh crivo.suaempresa.com.br
set -euo pipefail
cd "$(dirname "$0")/.."

DOMINIO="${1:-}"
if [[ -z "$DOMINIO" ]]; then
  echo "Uso: $0 <domínio>   (ex.: $0 crivo.suaempresa.com.br)" >&2
  exit 1
fi
[[ -f .env ]] || cp .env.example .env
chmod 600 .env

gerar() { openssl rand -hex 24; }
definir() {  # definir CHAVE valor [só se estiver vazio]
  local chave="$1" valor="$2" so_vazio="${3:-}"
  if grep -qE "^${chave}=" .env; then
    local atual; atual="$(grep -E "^${chave}=" .env | head -1 | cut -d= -f2-)"
    if [[ -n "$so_vazio" && -n "$atual" && "$atual" != "troque-esta-senha" ]]; then return; fi
    sed -i.bak "s|^${chave}=.*|${chave}=${valor}|" .env && rm -f .env.bak
  else
    echo "${chave}=${valor}" >> .env
  fi
}

definir CRIVO_DOMINIO "$DOMINIO"
definir PAINEL_URL "https://$DOMINIO"
definir COOKIE_SEGURO true
definir CORS_ORIGINS "https://$DOMINIO"
definir POSTGRES_PASSWORD "$(gerar)" so_vazio
definir ARGUS_WEBHOOK_SECRET "$(gerar)" so_vazio

SEGREDO="$(grep -E '^ARGUS_WEBHOOK_SECRET=' .env | cut -d= -f2-)"
TOKEN="$(grep -E '^ARGUS_TOKEN=' .env | cut -d= -f2- || true)"

cat <<FIM

.env pronto (só este servidor tem as senhas).

1) Aponte o DNS de $DOMINIO para o IP deste servidor e libere as portas 80 e 443.
2) Suba:   docker compose --profile https up -d --build
3) No Argus, cadastre o webhook "Tabulação Efetuada pelo Operador" com a URL:
   https://$DOMINIO/api/v1/webhooks/argus?secret=$SEGREDO
FIM
if [[ -z "$TOKEN" ]]; then
  echo "4) Preencha ARGUS_TOKEN (e ARGUS_CAMPAIGN_IDS) no .env e rode de novo o passo 2."
  echo "   Para conferir o token: docker compose exec backend python -m scripts.argus_diagnostico"
fi
