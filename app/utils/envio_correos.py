# utils/envio_correos.py
# ============================================================
#  Envío de correos vía Gmail SMTP (App Password)
#  Variables de entorno requeridas:
#    EMAIL_USER=tkdsystem1@gmail.com
#    EMAIL_PASS=szor cwul kwur gvoi   ← App Password de Google
#
#  En Render: Dashboard → Tu servicio → Environment → Add Env Var
#  NUNCA subas .env a Git.
# ============================================================

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from typing               import Dict, Any

GMAIL_USER = os.getenv("EMAIL_USER", "")
GMAIL_PASS = os.getenv("EMAIL_PASS", "")

SMTP_HOST  = "smtp.gmail.com"
SMTP_PORT  = 587          # TLS — funciona en Render (puerto 25 está bloqueado)


def send_resend_email(
    to:         str | list[str],
    subject:    str,
    html:       str,
    from_email: str = "Taekwondo System <tkdsystem1@gmail.com>",
) -> Dict[str, Any]:
    """
    Interfaz idéntica a la versión Resend — el resto del código
    no necesita cambiar ninguna llamada.
    """
    if not GMAIL_USER or not GMAIL_PASS:
        return {"success": False, "error": "EMAIL_USER o EMAIL_PASS no configurados en env vars"}

    # Extraer nombre y dirección del from_email
    # Acepta "Nombre <correo@gmail.com>" o solo "correo@gmail.com"
    from_name    = "Taekwondo System"
    from_address = GMAIL_USER
    if "<" in from_email and ">" in from_email:
        from_name    = from_email.split("<")[0].strip()
        from_address = from_email.split("<")[1].replace(">", "").strip()
    elif "@" in from_email:
        from_address = from_email.strip()

    # Gmail siempre envía desde GMAIL_USER sin importar from_address
    # (no permite spoofing), pero sí respeta el from_name en el header
    recipients = [to] if isinstance(to, str) else to

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{from_name} <{GMAIL_USER}>"
        msg["To"]      = ", ".join(recipients)

        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, recipients, msg.as_string())

        return {"success": True, "id": f"smtp-{GMAIL_USER}-{subject[:20]}"}

    except smtplib.SMTPAuthenticationError:
        return {
            "success": False,
            "error": "Autenticación fallida. Verifica EMAIL_USER y EMAIL_PASS en Render."
        }
    except smtplib.SMTPException as e:
        return {"success": False, "error": f"SMTP error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}