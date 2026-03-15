# ============================================================
#  app/utils/notificaciones.py
#  Notificaciones vía RESEND
#
#  IMPORTANTE — Sandbox de Resend:
#  Solo entrega correos a direcciones verificadas en tu cuenta Resend.
#  Para agregar correos de prueba:
#    resend.com → Settings → Verified Emails → Add email address
#
#  Cuando tengas dominio propio verificado en Resend, cambia:
#    from_email = "Dragon Negro Dojo <notificaciones@tudominio.com>"
# ============================================================

#  app/utils/notificaciones.py
#  Notificaciones vía RESEND (ya no usa SMTP Gmail)
# ============================================================

import os
from typing import Optional

# ✅ Mismo módulo que ya funciona en producción
from utils.envio_correos import send_resend_email

APP_URL = os.environ.get("APP_URL", "http://localhost:5173")


# ─────────────────────────────────────────────────────────────
#  HTML TEMPLATES  (sin cambios de diseño)
# ─────────────────────────────────────────────────────────────

def _html_pago_pendiente(
    nombre_alumno: str, nombre_escuela: str,
    concepto: str, monto: float,
    folio: str, fecha_vencimiento: str,
) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:0}}
  .w{{max-width:520px;margin:32px auto;background:#fff;border-radius:20px;
      box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden}}
  .h{{background:linear-gradient(135deg,#7c3aed,#06b6d4);padding:28px;text-align:center}}
  .h h1{{color:#fff;margin:0;font-size:20px;font-weight:900}}
  .h p{{color:rgba(255,255,255,.8);margin:6px 0 0;font-size:12px}}
  .b{{padding:24px}}
  .alert{{background:#fef3c7;border-left:4px solid #f59e0b;border-radius:10px;
          padding:12px 16px;margin-bottom:18px;font-size:13px;color:#92400e;font-weight:600}}
  .row{{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #f1f5f9}}
  .row span:first-child{{color:#64748b;font-size:13px}}
  .row span:last-child{{color:#0f172a;font-size:13px;font-weight:700}}
  .monto{{font-size:32px;font-weight:900;color:#7c3aed;text-align:center;padding:18px 0}}
  .foot{{background:#f8fafc;padding:14px;text-align:center;color:#94a3b8;
         font-size:11px;border-top:1px solid #e2e8f0}}
</style></head><body>
<div class="w">
  <div class="h"><h1>🥋 {nombre_escuela}</h1><p>Notificación de pago pendiente</p></div>
  <div class="b">
    <div class="alert">⚠️ Pago pendiente para <strong>{nombre_alumno}</strong></div>
    <div class="row"><span>Concepto</span><span>{concepto}</span></div>
    <div class="row"><span>Folio</span><span>{folio}</span></div>
    <div class="row"><span>Vencimiento</span><span>{fecha_vencimiento}</span></div>
    <div class="monto">${monto:,.0f} MXN</div>
  </div>
  <div class="foot">Generado automáticamente · TKW System</div>
</div></body></html>"""


def _html_formulario(
    nombre_alumno: str, nombre_escuela: str,
    ciclo: str, link_formulario: str,
) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:0}}
  .w{{max-width:520px;margin:32px auto;background:#fff;border-radius:20px;
      box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden}}
  .h{{background:linear-gradient(135deg,#059669,#06b6d4);padding:28px;text-align:center}}
  .h h1{{color:#fff;margin:0;font-size:20px;font-weight:900}}
  .h p{{color:rgba(255,255,255,.8);margin:6px 0 0;font-size:12px}}
  .b{{padding:24px;font-size:14px;color:#374151}}
  li{{padding:6px 0;font-size:13px;color:#374151}}
  .btn{{display:block;background:linear-gradient(135deg,#059669,#10b981);color:#fff;
        text-decoration:none;text-align:center;padding:13px;border-radius:12px;
        font-weight:900;font-size:14px;margin:20px 0}}
  .note{{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;
         padding:12px;font-size:12px;color:#166534}}
  .foot{{background:#f8fafc;padding:14px;text-align:center;color:#94a3b8;
         font-size:11px;border-top:1px solid #e2e8f0}}
</style></head><body>
<div class="w">
  <div class="h"><h1>🥋 {nombre_escuela}</h1><p>Formulario de inscripción {ciclo}</p></div>
  <div class="b">
    <p>Estimado tutor de <strong>{nombre_alumno}</strong>, completa el formulario
    de inscripción para el ciclo <strong>{ciclo}</strong>.</p>
    <ol>
      <li>Abre el formulario y llena todos los campos.</li>
      <li>Imprímelo y <strong>fírmalo de puño y letra</strong>.</li>
      <li>Toma foto clara y súbela desde el mismo link.</li>
    </ol>
    <a href="{link_formulario}" class="btn">📋 Abrir formulario →</a>
    <div class="note">✅ La academia validará tu formulario en breve.</div>
  </div>
  <div class="foot">Generado automáticamente · TKW System</div>
</div></body></html>"""


def _html_recordatorio(
    nombre_alumno: str, nombre_escuela: str,
    monto: float, dias_vencido: int,
) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:0}}
  .w{{max-width:520px;margin:32px auto;background:#fff;border-radius:20px;
      box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden}}
  .h{{background:linear-gradient(135deg,#dc2626,#f97316);padding:28px;text-align:center}}
  .h h1{{color:#fff;margin:0;font-size:20px;font-weight:900}}
  .h p{{color:rgba(255,255,255,.8);margin:6px 0 0;font-size:12px}}
  .b{{padding:24px;text-align:center}}
  .dias{{font-size:48px;font-weight:900;color:#dc2626;padding:12px 0}}
  .label{{font-size:13px;color:#64748b;margin-bottom:4px}}
  .monto{{font-size:28px;font-weight:900;color:#0f172a;padding:8px 0}}
  .msg{{font-size:13px;color:#64748b;margin-top:16px;line-height:1.6}}
  .foot{{background:#f8fafc;padding:14px;text-align:center;color:#94a3b8;
         font-size:11px;border-top:1px solid #e2e8f0}}
</style></head><body>
<div class="w">
  <div class="h"><h1>🥋 {nombre_escuela}</h1><p>Recordatorio de pago vencido</p></div>
  <div class="b">
    <div class="label">Alumno: <strong>{nombre_alumno}</strong></div>
    <div class="dias">{dias_vencido}</div>
    <div class="label">días de atraso</div>
    <div class="monto">${monto:,.0f} MXN pendiente</div>
    <div class="msg">Por favor regulariza tu situación a la brevedad.<br>
    Si ya realizaste el pago, ignora este mensaje.</div>
  </div>
  <div class="foot">Generado automáticamente · TKW System</div>
</div></body></html>"""


# ─────────────────────────────────────────────────────────────
#  COMPATIBILIDAD: send_email — usado por scheduler.py
#  Redirige al nuevo send_resend_email sin romper imports existentes
# ─────────────────────────────────────────────────────────────

def send_email(to_email: str, subject: str, html_body: str, from_name: str = "TKW Sistema") -> bool:
    """Alias de compatibilidad para scheduler.py y otros módulos que usaban send_email."""
    result = send_resend_email(
        to=to_email,
        subject=subject,
        html=html_body,
        from_email="TKW Sistema <onboarding@resend.dev>",
    )
    return result.get("success", False)


# ─────────────────────────────────────────────────────────────
#  ORQUESTADORES  (ahora usan send_resend_email)
# ─────────────────────────────────────────────────────────────

def notificar_pago_pendiente(
    correo_tutor:      Optional[str],
    nombre_alumno:     str,
    nombre_escuela:    str,
    concepto:          str,
    monto:             float,
    folio:             str,
    fecha_vencimiento: str,
    canal:             str = "email",          # canal ignorado, siempre email
) -> dict:
    result = {"email": None, "error": None}
    if not correo_tutor:
        result["error"] = "Sin correo del tutor registrado"
        return result
    r = send_resend_email(
        to      = correo_tutor,
        subject = f"Pago pendiente — {concepto} | {nombre_escuela}",
        html    = _html_pago_pendiente(
            nombre_alumno, nombre_escuela,
            concepto, monto, folio, fecha_vencimiento,
        ),
        from_email = "TKW Sistema <onboarding@resend.dev>",
    )
    result["email"] = r.get("success", False)
    result["error"] = r.get("error")
    return result


def notificar_formulario_inscripcion(
    correo_tutor:    Optional[str],
    nombre_alumno:   str,
    nombre_escuela:  str,
    ciclo:           str,
    link_formulario: str,
) -> dict:
    result = {"email": None, "error": None}
    if not correo_tutor:
        result["error"] = "Sin correo del tutor registrado"
        return result
    r = send_resend_email(
        to      = correo_tutor,
        subject = f"Formulario inscripción {ciclo} — {nombre_escuela}",
        html    = _html_formulario(nombre_alumno, nombre_escuela, ciclo, link_formulario),
        from_email = "TKW Sistema <onboarding@resend.dev>",
    )
    result["email"] = r.get("success", False)
    result["error"] = r.get("error")
    return result


def notificar_recordatorio(
    correo_tutor:   Optional[str],
    nombre_alumno:  str,
    nombre_escuela: str,
    monto:          float,
    dias_vencido:   int,
) -> dict:
    result = {"email": None, "error": None}
    if not correo_tutor:
        result["error"] = "Sin correo del tutor registrado"
        return result
    r = send_resend_email(
        to      = correo_tutor,
        subject = f"Recordatorio de pago — {nombre_alumno} | {nombre_escuela}",
        html    = _html_recordatorio(nombre_alumno, nombre_escuela, monto, dias_vencido),
        from_email = "TKW Sistema <onboarding@resend.dev>",
    )
    result["email"] = r.get("success", False)
    result["error"] = r.get("error")
    return result