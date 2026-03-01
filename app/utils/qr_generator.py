# ============================================================
#  app/utils/qr_generator.py
#  Genera QR como PDF y ahora lo incluye en el cuerpo del email
# ============================================================

import os
import io
import uuid
from typing import Optional
import qrcode
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

APP_URL = os.environ.get("APP_URL", "http://localhost:5173")


# ─────────────────────────────────────────────────────────────
#  HELPERS QR
# ─────────────────────────────────────────────────────────────

def generar_token_qr() -> str:
    """Genera un UUID único para el QR."""
    return str(uuid.uuid4())

def generar_imagen_qr(token: str) -> Image.Image:
    """Genera imagen PIL del QR a partir del token."""
    url = f"{APP_URL}/torneos/validar-qr/{token}"
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


# ─────────────────────────────────────────────────────────────
#  GENERAR PDF
# ─────────────────────────────────────────────────────────────

def generar_pdf_qr(
    token: str, nombre_alumno: str, nombre_torneo: str,
    fecha_torneo: str, hora_torneo: str, sede_torneo: str,
    ciudad_torneo: str, cinta: str, edad: int,
    peso: Optional[float] = None,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    centered = ParagraphStyle("centered", parent=styles["Normal"], alignment=TA_CENTER)
    title_style = ParagraphStyle("title", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=22, textColor=colors.HexColor("#7c3aed"), spaceAfter=4)
    subtitle_style = ParagraphStyle("subtitle", parent=styles["Normal"], alignment=TA_CENTER, fontSize=13, textColor=colors.HexColor("#64748b"), spaceAfter=16)
    label_style = ParagraphStyle("label", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#64748b"))
    value_style = ParagraphStyle("value", parent=styles["Normal"], fontSize=12, textColor=colors.HexColor("#0f172a"), fontName="Helvetica-Bold")

    qr_img = generar_imagen_qr(token)
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_rl = RLImage(qr_buffer, width=6*cm, height=6*cm)

    peso_str = f"{peso:.1f} kg" if peso else "No registrado"
    data_table = [
        [Paragraph("Participante", label_style),  Paragraph(nombre_alumno, value_style)],
        [Paragraph("Torneo",       label_style),  Paragraph(nombre_torneo,  value_style)],
        [Paragraph("Fecha",        label_style),  Paragraph(f"{fecha_torneo} — {hora_torneo}", value_style)],
        [Paragraph("Sede",         label_style),  Paragraph(f"{sede_torneo}, {ciudad_torneo}", value_style)],
        [Paragraph("Cinta",        label_style),  Paragraph(cinta,           value_style)],
        [Paragraph("Edad",         label_style),  Paragraph(f"{edad} años",  value_style)],
        [Paragraph("Peso",         label_style),  Paragraph(peso_str,        value_style)],
    ]
    table = Table(data_table, colWidths=[4*cm, 11*cm])
    table.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f8fafc"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", (0, 0), (-1, -1), 6),
    ]))

    story = [
        Paragraph("🥋 TKW System", title_style),
        Paragraph("Credencial de acceso al torneo", subtitle_style),
        qr_rl, Spacer(1, 0.5*cm),
        Paragraph("Presenta este QR en la entrada del evento", centered),
        Spacer(1, 0.8*cm), table,
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ─────────────────────────────────────────────────────────────
#  ENVIAR QR POR CORREO (INLINE + PDF)
# ─────────────────────────────────────────────────────────────

def _html_qr_torneo(
    nombre_alumno: str, nombre_torneo: str,
    fecha_torneo: str, hora_torneo: str,
    sede_torneo: str, ciudad_torneo: str,
) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:0}}
  .w{{max-width:520px;margin:32px auto;background:#fff;border-radius:20px;box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden}}
  .h{{background:linear-gradient(135deg,#7c3aed,#06b6d4);padding:28px;text-align:center}}
  .h h1{{color:#fff;margin:0;font-size:20px;font-weight:900}}
  .b{{padding:24px;text-align:center}}
  .qr-box{{background:#f8fafc;padding:20px;border-radius:15px;margin:20px 0;display:inline-block;border:1px solid #e2e8f0}}
  .row{{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #f1f5f9;text-align:left}}
  .row span:first-child{{color:#64748b;font-size:13px}}
  .row span:last-child{{color:#0f172a;font-size:13px;font-weight:700}}
  .foot{{background:#f8fafc;padding:14px;text-align:center;color:#94a3b8;font-size:11px;border-top:1px solid #e2e8f0}}
</style></head><body>
<div class="w">
  <div class="h"><h1>🏆 ¡Inscripción confirmada!</h1><p style="color:white">{nombre_torneo}</p></div>
  <div class="b">
    <p style="font-size:14px;color:#374151">Hola, <strong>{nombre_alumno}</strong> ya tiene su pase listo.</p>
    
    <!-- QR VISIBLE EN EL CUERPO -->
    <div class="qr-box">
      <img src="cid:qr_image" width="200" height="200" alt="QR de acceso">
      <p style="font-size:11px;color:#64748b;margin-top:10px">Escanea este código en la entrada</p>
    </div>

    <div class="row"><span>Torneo</span><span>{nombre_torneo}</span></div>
    <div class="row"><span>Fecha</span><span>{fecha_torneo}</span></div>
    <div class="row"><span>Sede</span><span>{sede_torneo}</span></div>
    <p style="font-size:12px;color:#64748b;margin-top:20px">También hemos adjuntado una copia en PDF para tu comodidad.</p>
  </div>
  <div class="foot">Dragon Negro Dojo · TKW System</div>
</div></body></html>"""


def enviar_qr_por_correo(
    token: str, correo_tutor: str, nombre_alumno: str,
    nombre_torneo: str, fecha_torneo: str, hora_torneo: str,
    sede_torneo: str, ciudad_torneo: str, pdf_bytes: bytes,
    from_name: str = "TKW Sistema",
) -> bool:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email.mime.image import MIMEImage
    from email import encoders

    EMAIL_USER = os.environ.get("EMAIL_USER", "")
    EMAIL_PASS = os.environ.get("EMAIL_PASS", "")

    if not EMAIL_USER or not EMAIL_PASS: return False

    try:
        # Usamos 'related' para que la imagen inline funcione correctamente
        msg = MIMEMultipart("related")
        msg["Subject"] = f"🏆 QR de acceso — {nombre_torneo} | {nombre_alumno}"
        msg["From"] = f"{from_name} <{EMAIL_USER}>"
        msg["To"] = correo_tutor

        # Contenedor para el cuerpo (HTML + Imagen inline)
        msg_alternative = MIMEMultipart("alternative")
        msg.attach(msg_alternative)

        # Cuerpo HTML con referencia cid:qr_image
        html_body = _html_qr_torneo(nombre_alumno, nombre_torneo, fecha_torneo, hora_torneo, sede_torneo, ciudad_torneo)
        msg_alternative.attach(MIMEText(html_body, "html"))

        # Generar imagen QR para el cuerpo
        qr_img = generar_imagen_qr(token)
        qr_img_bytes = io.BytesIO()
        qr_img.save(qr_img_bytes, format="PNG")
        
        img_part = MIMEImage(qr_img_bytes.getvalue())
        img_part.add_header("Content-ID", "<qr_image>") # Debe coincidir con cid:qr_image en el HTML
        img_part.add_header("Content-Disposition", "inline", filename="qr.png")
        msg.attach(img_part)

        # PDF adjunto
        pdf_part = MIMEBase("application", "pdf")
        pdf_part.set_payload(pdf_bytes)
        encoders.encode_base64(pdf_part)
        pdf_part.add_header("Content-Disposition", f"attachment; filename=Pase_{nombre_alumno.replace(' ', '_')}.pdf")
        msg.attach(pdf_part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(EMAIL_USER, EMAIL_PASS)
            srv.sendmail(EMAIL_USER, correo_tutor, msg.as_string())

        return True
    except Exception as e:
        print(f"[ERROR EMAIL] {e}")
        return False