# ============================================================
#  app/utils/qr_generator.py
#  Genera QR como PDF y lo envía vía RESEND (no SMTP)
# ============================================================

import os
import io
import uuid
import base64
from typing import Optional

import qrcode
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Image as RLImage, Table, TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

# ✅ Reutilizamos el mismo send_resend_email que ya funciona
from utils.envio_correos import send_resend_email

APP_URL = os.environ.get("APP_URL", "http://localhost:5173")


# ─────────────────────────────────────────────────────────────
#  HELPERS QR
# ─────────────────────────────────────────────────────────────

def generar_token_qr() -> str:
    return str(uuid.uuid4())


def generar_imagen_qr(token: str) -> Image.Image:
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


def _qr_as_base64_png(token: str) -> str:
    """
    Convierte el QR a data URI base64.
    Resend no soporta imágenes inline CID, así que usamos data URI
    directamente en el src del <img>.
    """
    img = generar_imagen_qr(token)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


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
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm,   bottomMargin=2*cm,
    )
    styles     = getSampleStyleSheet()
    centered   = ParagraphStyle("centered",  parent=styles["Normal"], alignment=TA_CENTER)
    title_s    = ParagraphStyle("title",     parent=styles["Heading1"], alignment=TA_CENTER,
                                fontSize=22, textColor=colors.HexColor("#7c3aed"), spaceAfter=4)
    subtitle_s = ParagraphStyle("subtitle",  parent=styles["Normal"], alignment=TA_CENTER,
                                fontSize=13, textColor=colors.HexColor("#64748b"), spaceAfter=16)
    label_s    = ParagraphStyle("label",     parent=styles["Normal"], fontSize=10,
                                textColor=colors.HexColor("#64748b"))
    value_s    = ParagraphStyle("value",     parent=styles["Normal"], fontSize=12,
                                textColor=colors.HexColor("#0f172a"), fontName="Helvetica-Bold")

    qr_img = generar_imagen_qr(token)
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    qr_rl = RLImage(qr_buf, width=6*cm, height=6*cm)

    peso_str = f"{peso:.1f} kg" if peso else "No registrado"
    data_table = [
        [Paragraph("Participante", label_s), Paragraph(nombre_alumno,                      value_s)],
        [Paragraph("Torneo",       label_s), Paragraph(nombre_torneo,                      value_s)],
        [Paragraph("Fecha",        label_s), Paragraph(f"{fecha_torneo} — {hora_torneo}",  value_s)],
        [Paragraph("Sede",         label_s), Paragraph(f"{sede_torneo}, {ciudad_torneo}",  value_s)],
        [Paragraph("Cinta",        label_s), Paragraph(cinta,                              value_s)],
        [Paragraph("Edad",         label_s), Paragraph(f"{edad} años",                     value_s)],
        [Paragraph("Peso",         label_s), Paragraph(peso_str,                           value_s)],
    ]
    table = Table(data_table, colWidths=[4*cm, 11*cm])
    table.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f8fafc"), colors.white]),
        ("GRID",           (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))

    doc.build([
        Paragraph("🥋 TKW System", title_s),
        Paragraph("Credencial de acceso al torneo", subtitle_s),
        qr_rl, Spacer(1, 0.5*cm),
        Paragraph("Presenta este QR en la entrada del evento", centered),
        Spacer(1, 0.8*cm), table,
    ])
    buffer.seek(0)
    return buffer.read()


# ─────────────────────────────────────────────────────────────
#  HTML TEMPLATES
# ─────────────────────────────────────────────────────────────

def _html_qr_torneo(
    nombre_alumno: str, nombre_torneo: str,
    fecha_torneo: str, sede_torneo: str,
    qr_data_uri: str,           # ← base64 data URI, no CID
) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:0}}
  .w{{max-width:520px;margin:32px auto;background:#fff;border-radius:20px;
      box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden}}
  .h{{background:linear-gradient(135deg,#7c3aed,#06b6d4);padding:28px;text-align:center}}
  .h h1{{color:#fff;margin:0;font-size:20px;font-weight:900}}
  .h p{{color:rgba(255,255,255,.8);margin:6px 0 0;font-size:13px}}
  .b{{padding:24px;text-align:center}}
  .qr-box{{background:#f8fafc;padding:20px;border-radius:15px;
           margin:20px auto;display:inline-block;border:1px solid #e2e8f0}}
  .row{{display:flex;justify-content:space-between;padding:9px 0;
        border-bottom:1px solid #f1f5f9;text-align:left}}
  .row span:first-child{{color:#64748b;font-size:13px}}
  .row span:last-child{{color:#0f172a;font-size:13px;font-weight:700}}
  .foot{{background:#f8fafc;padding:14px;text-align:center;
         color:#94a3b8;font-size:11px;border-top:1px solid #e2e8f0}}
</style></head><body>
<div class="w">
  <div class="h">
    <h1>🏆 ¡Inscripción confirmada!</h1>
    <p>{nombre_torneo}</p>
  </div>
  <div class="b">
    <p style="font-size:14px;color:#374151">
      Hola, <strong>{nombre_alumno}</strong> ya tiene su pase listo.
    </p>
    <div class="qr-box">
      <img src="{qr_data_uri}" width="200" height="200" alt="QR de acceso">
      <p style="font-size:11px;color:#64748b;margin-top:10px">
        Escanea este código en la entrada
      </p>
    </div>
    <div class="row"><span>Torneo</span><span>{nombre_torneo}</span></div>
    <div class="row"><span>Fecha</span><span>{fecha_torneo}</span></div>
    <div class="row"><span>Sede</span><span>{sede_torneo}</span></div>
    <p style="font-size:12px;color:#64748b;margin-top:20px">
      También hemos adjuntado una copia en PDF para tu comodidad.
    </p>
  </div>
  <div class="foot">Dragon Negro Dojo · TKW System</div>
</div></body></html>"""


def _html_cobro_confirmado(
    nombre_alumno: str, concepto: str, monto: float,
    metodo_pago: str, folio: str,
    nombre_escuela: str = "Dragon Negro Dojo",
) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:0}}
  .w{{max-width:520px;margin:32px auto;background:#fff;border-radius:20px;
      box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden}}
  .h{{background:linear-gradient(135deg,#059669,#06b6d4);padding:28px;text-align:center}}
  .h h1{{color:#fff;margin:0;font-size:20px;font-weight:900}}
  .h p{{color:rgba(255,255,255,.8);margin:6px 0 0;font-size:12px}}
  .b{{padding:24px}}
  .check{{font-size:52px;text-align:center;padding:16px 0}}
  .row{{display:flex;justify-content:space-between;padding:9px 0;
        border-bottom:1px solid #f1f5f9}}
  .row span:first-child{{color:#64748b;font-size:13px}}
  .row span:last-child{{color:#0f172a;font-size:13px;font-weight:700}}
  .monto{{font-size:38px;font-weight:900;color:#059669;text-align:center;padding:20px 0}}
  .note{{font-size:12px;color:#64748b;text-align:center;margin-top:0}}
  .foot{{background:#f8fafc;padding:14px;text-align:center;
         color:#94a3b8;font-size:11px;border-top:1px solid #e2e8f0}}
</style></head><body>
<div class="w">
  <div class="h">
    <h1>🥋 {nombre_escuela}</h1>
    <p>Confirmación de pago</p>
  </div>
  <div class="b">
    <div class="check">✅</div>
    <div class="row"><span>Alumno</span><span>{nombre_alumno}</span></div>
    <div class="row"><span>Concepto</span><span>{concepto}</span></div>
    <div class="row"><span>Folio</span><span>{folio}</span></div>
    <div class="row"><span>Método de pago</span><span>{metodo_pago}</span></div>
    <div class="monto">${monto:,.2f} MXN</div>
    <p class="note">Pago registrado exitosamente. Conserva este correo como comprobante.</p>
  </div>
  <div class="foot">Generado automáticamente · TKW System</div>
</div></body></html>"""


# ─────────────────────────────────────────────────────────────
#  ENVÍO VÍA RESEND
# ─────────────────────────────────────────────────────────────

def enviar_qr_por_correo(
    token: str,
    correo_tutor: str,
    nombre_alumno: str,
    nombre_torneo: str,
    fecha_torneo: str,
    hora_torneo: str,
    sede_torneo: str,
    ciudad_torneo: str,
    pdf_bytes: bytes,
    from_name: str = "Dragon Negro Dojo",
) -> bool:
    """
    Envía QR + PDF del torneo usando Resend.
    - El QR se incrusta como base64 data URI (Resend no soporta CID inline).
    - El PDF va como attachment en base64.
    """
    try:
        import resend as resend_sdk
        import os
        resend_sdk.api_key = os.environ.get("RESEND_API_KEY", "")

        if not resend_sdk.api_key:
            print("[QR EMAIL] RESEND_API_KEY no configurada")
            return False

        qr_data_uri = _qr_as_base64_png(token)
        html = _html_qr_torneo(
            nombre_alumno, nombre_torneo,
            fecha_torneo, sede_torneo, qr_data_uri,
        )
        pdf_b64   = base64.b64encode(pdf_bytes).decode()
        filename  = f"Pase_{nombre_alumno.replace(' ', '_')}.pdf"

        response = resend_sdk.Emails.send({
            "from":    f"{from_name} <onboarding@resend.dev>",
            "to":      [correo_tutor],
            "subject": f"🏆 QR de acceso — {nombre_torneo} | {nombre_alumno}",
            "html":    html,
            "attachments": [{"filename": filename, "content": pdf_b64}],
        })
        print(f"[QR EMAIL ✓] id={response.get('id')} → {correo_tutor}")
        return True

    except Exception as e:
        print(f"[QR EMAIL ✗] {e}")
        return False


def enviar_confirmacion_cobro(
    correo_tutor: str,
    nombre_alumno: str,
    concepto: str,
    monto: float,
    metodo_pago: str,
    folio: str,
    nombre_escuela: str = "Dragon Negro Dojo",
) -> bool:
    """
    Confirmación de cobro para mensualidades, inscripciones, exámenes, etc.
    Usa send_resend_email del módulo envio_correos.
    """
    try:
        html   = _html_cobro_confirmado(
            nombre_alumno, concepto, monto,
            metodo_pago, folio, nombre_escuela,
        )
        result = send_resend_email(
            to      = correo_tutor,
            subject = f"✅ Pago confirmado — {concepto} | {nombre_alumno}",
            html    = html,
            from_email = f"{nombre_escuela} <onboarding@resend.dev>",
        )
        ok = result.get("success", False)
        if ok:
            print(f"[COBRO EMAIL ✓] id={result.get('id')} → {correo_tutor}")
        else:
            print(f"[COBRO EMAIL ✗] {result.get('error')}")
        return ok

    except Exception as e:
        print(f"[COBRO EMAIL ✗] {e}")
        return False