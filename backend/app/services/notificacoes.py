"""Envio de alertas e relatórios por webhook (Slack, Teams, Google Chat) e/ou e-mail (SMTP).

Sem nada configurado, nada é enviado: alertas e relatórios continuam visíveis no painel.
Credenciais (SMTP_SENHA, URL do webhook) ficam só no .env, nunca no repositório.
"""
import logging
import smtplib
from email.message import EmailMessage

import httpx

from ..config import settings
from . import status

log = logging.getLogger("notificacoes")
CHAVE_STATUS = "notificacoes"


def _emails() -> list[str]:
    return [e.strip() for e in settings.notificar_emails.split(",") if e.strip()]


def canais() -> dict[str, bool]:
    return {"webhook": bool(settings.notificar_webhook_url),
            "email": bool(settings.smtp_host and _emails())}


def _webhook(assunto: str, texto: str) -> None:
    # {"text": ...} é aceito pelos webhooks de entrada do Slack, Microsoft Teams e Google Chat
    r = httpx.post(settings.notificar_webhook_url, json={"text": f"*{assunto}*\n{texto}"}, timeout=15)
    r.raise_for_status()


def _email(assunto: str, texto: str, html: str | None) -> None:
    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = settings.smtp_remetente or settings.smtp_usuario
    msg["To"] = ", ".join(_emails())
    msg.set_content(texto)
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_porta, timeout=20) as s:
        if settings.smtp_tls:
            s.starttls()
        if settings.smtp_usuario:
            s.login(settings.smtp_usuario, settings.smtp_senha)
        s.send_message(msg)


def enviar(assunto: str, texto: str, html: str | None = None) -> dict:
    """Envia por todos os canais configurados. Falha em um canal não impede os outros."""
    ativos = [c for c, ok in canais().items() if ok]
    if not ativos:
        return {"enviado": False, "canais": [], "motivo": "Nenhum canal configurado (NOTIFICAR_WEBHOOK_URL ou SMTP_*)."}
    enviados, erros = [], {}
    for canal in ativos:
        try:
            _webhook(assunto, texto) if canal == "webhook" else _email(assunto, texto, html)
            enviados.append(canal)
        except Exception as e:
            log.exception("falha ao notificar por %s", canal)
            erros[canal] = f"{type(e).__name__}: {str(e)[:200]}"
    status.registrar(CHAVE_STATUS, not erros, "; ".join(f"{k}: {v}" for k, v in erros.items())
                     or f"Enviado por {', '.join(enviados)}: {assunto}")
    return {"enviado": bool(enviados) and not erros, "canais": enviados, "erros": erros}


def link(caminho: str | None) -> str:
    """Link absoluto para o painel, quando PAINEL_URL estiver configurado."""
    if not caminho:
        return ""
    base = settings.painel_url.rstrip("/")
    return f"{base}{caminho}" if base else caminho
