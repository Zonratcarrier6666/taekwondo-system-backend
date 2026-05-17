import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

def send_resend_email(
    to: str | list[str],
    subject: str,
    html: str,
    from_email: str = "TKW Sistema <tkdsystem1@gmail.com>",
) -> Dict[str, Any]:
    
    EMAIL_USER = os.getenv("EMAIL_USER")  # ← adentro de la función
    EMAIL_PASS = os.getenv("EMAIL_PASS")  # ← adentro de la función
    
    print("USER:", EMAIL_USER)
    print("PASS:", EMAIL_PASS)  # ← confirma que ya es la nueva

    if not EMAIL_USER or not EMAIL_PASS:
        return {"error": "EMAIL_USER o EMAIL_PASS no configurados en env vars"}

    destinatarios = [to] if isinstance(to, str) else to

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = from_email
        msg["To"]      = ", ".join(destinatarios)
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, destinatarios, msg.as_string())

        return {"success": True, "id": None}
    except Exception as e:
        return {"error": str(e)}