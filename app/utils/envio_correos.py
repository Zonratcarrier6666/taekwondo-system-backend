import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Cargamos las variables del archivo .env
load_dotenv()

# Configuración del servidor (Generalmente fija)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Variables sensibles obtenidas del entorno
SENDER_EMAIL = os.getenv("EMAIL_USER")
SENDER_PASSWORD = os.getenv("EMAIL_PASS") 

def enviar_pase_torneo(email_destino, datos_pase):
    """
    Envía un correo HTML con el pase de acceso y el código QR.
    Extrae las credenciales de forma segura desde el entorno.
    """
    # Verificación de seguridad: si las variables no existen, lanzamos un error claro
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("ERROR: No se han configurado EMAIL_USER o EMAIL_PASS en el .env")
        return False

    msg = MIMEMultipart()
    msg['From'] = f"Sistema TKD <{SENDER_EMAIL}>"
    msg['To'] = email_destino
    msg['Subject'] = f"🎫 Pase de Acceso: {datos_pase['torneo_nombre']}"

    # URL dinámica para el QR basado en el token
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={datos_pase['token_qr']}"

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; border-radius: 10px; overflow: hidden; border: 1px solid #eee;">
            <div style="background-color: #1d4ed8; color: white; padding: 25px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px;">¡Registro Completado!</h1>
                <p style="margin: 5px 0 0; opacity: 0.8;">Tu pase oficial de acceso al evento</p>
            </div>
            <div style="padding: 30px; text-align: center; background-color: #ffffff;">
                <h2 style="color: #1d4ed8; margin-top: 0;">{datos_pase['torneo_nombre']}</h2>
                <p>Hola <strong>{datos_pase['tutor_nombre']}</strong>,</p>
                <p>Confirmamos el registro exitoso de <strong>{datos_pase['alumno_nombre']}</strong>.</p>
                
                <div style="background-color: #f8fafc; border: 2px dashed #cbd5e1; padding: 25px; margin: 25px 0; border-radius: 12px;">
                    <p style="font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 15px;">Presenta este código en la entrada</p>
                    <img src="{qr_url}" alt="QR Code" style="width: 180px; height: 180px; display: block; margin: 0 auto;" />
                    <p style="font-weight: bold; font-family: 'Courier New', monospace; color: #334155; margin-top: 15px;">
                        {datos_pase['token_qr']}
                    </p>
                </div>

                <div style="text-align: left; background-color: #f1f5f9; padding: 15px; border-radius: 8px;">
                    <p style="margin: 5px 0;">📍 <strong>Lugar:</strong> {datos_pase['sede']}</p>
                    <p style="margin: 5px 0;">📅 <strong>Fecha:</strong> {datos_pase['fecha']}</p>
                    <p style="margin: 5px 0;">🥋 <strong>Categoría:</strong> {datos_pase['categoria']}</p>
                </div>

                <p style="font-size: 11px; color: #94a3b8; margin-top: 30px; font-style: italic;">
                    * Este código es personal e intransferible. El acceso se validará en la entrada el día del evento.
                </p>
            </div>
            <div style="background-color: #f8fafc; padding: 15px; text-align: center; font-size: 11px; color: #64748b; border-top: 1px solid #f1f5f9;">
                Enviado automáticamente por <strong>{datos_pase['escuela_nombre']}</strong>.
            </div>
        </div>
    </body>
    </html>
    """
    
    msg.attach(MIMEText(html, 'html'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, email_destino, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"DEBUG: Error SMTP: {str(e)}")
        return False