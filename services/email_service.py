import json
import os
from urllib import error, request


RESEND_API_URL = "https://api.resend.com/emails"


def enviar_email_resend(destinatario, assunto, html, texto=None):
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    remetente = os.environ.get("RESEND_FROM_EMAIL", "").strip()

    if not api_key or not remetente:
        print("Resend nao configurado: defina RESEND_API_KEY e RESEND_FROM_EMAIL.")
        return False

    payload = {
        "from": remetente,
        "to": [destinatario],
        "subject": assunto,
        "html": html,
    }
    if texto:
        payload["text"] = texto

    requisicao = request.Request(
        RESEND_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(requisicao, timeout=12) as resposta:
            return 200 <= resposta.status < 300
    except error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", errors="replace")
        print(f"Falha ao enviar email pelo Resend: HTTP {exc.code} - {detalhe}")
    except error.URLError as exc:
        print(f"Falha ao enviar email pelo Resend: {exc}")
    return False
