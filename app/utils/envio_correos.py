# utils/email_utils.py (o un archivo similar)
import os
import resend
from typing import Dict, Any

# Carga la key desde env (Render la provee)
resend.api_key = os.getenv("RESEND_API_KEY")

def send_resend_email(
    to: str | list[str],
    subject: str,
    html: str,
    from_email: str = "Taekwondo System <onboarding@resend.dev>",  # Temporal, cámbialo después
) -> Dict[str, Any]:
    if not resend.api_key:
        return {"error": "RESEND_API_KEY no está configurada en env vars"}

    params = {
        "from": from_email,
        "to": [to] if isinstance(to, str) else to,
        "subject": subject,
        "html": html,
    }

    try:
        response = resend.Emails.send(params)
        return {"success": True, "id": response["id"]}
    except Exception as e:
        return {"error": str(e)}