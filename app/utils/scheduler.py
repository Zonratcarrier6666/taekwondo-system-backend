# ============================================================
#  app/utils/scheduler.py
#  Corre cada día a las 9:00 AM y revisa todos los pagos
#  pendientes para enviar notificaciones automáticas.
#
#  Lógica:
#   -5 días antes del vencimiento → aviso "paga pronto"
#    1-5 días después             → aviso diario "tienes atraso"
#    6+ días después              → aviso diario "riesgo de baja"
#
#  Se detiene automáticamente cuando estatus=1 (pagado)
# ============================================================

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date, timedelta
from typing import Optional
import os

from app.utils.notificaciones import send_email
from app.utils.database import get_db

APP_URL = os.environ.get("APP_URL", "http://localhost:5173")

# ─── Instancia global del scheduler ──────────────────────────
scheduler = AsyncIOScheduler(timezone="America/Mexico_City")


# ─────────────────────────────────────────────────────────────
#  HTML TEMPLATES ESPECÍFICOS
# ─────────────────────────────────────────────────────────────

def _html_aviso_pronto(
    nombre_alumno: str, nombre_escuela: str,
    concepto: str, monto: float,
    fecha_vencimiento: str, dias_restantes: int,
) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:0}}
  .w{{max-width:520px;margin:32px auto;background:#fff;border-radius:20px;
      box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden}}
  .h{{background:linear-gradient(135deg,#f59e0b,#f97316);padding:28px;text-align:center}}
  .h h1{{color:#fff;margin:0;font-size:20px;font-weight:900}}
  .h p{{color:rgba(255,255,255,.9);margin:6px 0 0;font-size:12px}}
  .b{{padding:24px;text-align:center}}
  .dias{{font-size:64px;font-weight:900;color:#f59e0b;line-height:1}}
  .dias-label{{font-size:14px;color:#64748b;margin-bottom:20px}}
  .row{{display:flex;justify-content:space-between;padding:9px 0;
        border-bottom:1px solid #f1f5f9;text-align:left}}
  .row span:first-child{{color:#64748b;font-size:13px}}
  .row span:last-child{{color:#0f172a;font-size:13px;font-weight:700}}
  .monto{{font-size:28px;font-weight:900;color:#f59e0b;padding:16px 0}}
  .foot{{background:#f8fafc;padding:14px;text-align:center;color:#94a3b8;
         font-size:11px;border-top:1px solid #e2e8f0}}
</style></head><body>
<div class="w">
  <div class="h">
    <h1>🥋 {nombre_escuela}</h1>
    <p>Recordatorio de pago próximo</p>
  </div>
  <div class="b">
    <div class="dias">{dias_restantes}</div>
    <div class="dias-label">días para que venza tu pago</div>
    <div class="row"><span>Alumno</span><span>{nombre_alumno}</span></div>
    <div class="row"><span>Concepto</span><span>{concepto}</span></div>
    <div class="row"><span>Vence el</span><span>{fecha_vencimiento}</span></div>
    <div class="monto">${monto:,.0f} MXN</div>
    <p style="font-size:13px;color:#64748b">
      Realiza tu pago antes de la fecha límite para evitar recargos.
    </p>
  </div>
  <div class="foot">Generado automáticamente · TKW System</div>
</div></body></html>"""


def _html_aviso_atraso(
    nombre_alumno: str, nombre_escuela: str,
    concepto: str, monto: float,
    fecha_vencimiento: str, dias_atraso: int,
) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:0}}
  .w{{max-width:520px;margin:32px auto;background:#fff;border-radius:20px;
      box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden}}
  .h{{background:linear-gradient(135deg,#dc2626,#f97316);padding:28px;text-align:center}}
  .h h1{{color:#fff;margin:0;font-size:20px;font-weight:900}}
  .h p{{color:rgba(255,255,255,.9);margin:6px 0 0;font-size:12px}}
  .b{{padding:24px;text-align:center}}
  .dias{{font-size:64px;font-weight:900;color:#dc2626;line-height:1}}
  .dias-label{{font-size:14px;color:#64748b;margin-bottom:20px}}
  .row{{display:flex;justify-content:space-between;padding:9px 0;
        border-bottom:1px solid #f1f5f9;text-align:left}}
  .row span:first-child{{color:#64748b;font-size:13px}}
  .row span:last-child{{color:#0f172a;font-size:13px;font-weight:700}}
  .monto{{font-size:28px;font-weight:900;color:#dc2626;padding:16px 0}}
  .alert{{background:#fef2f2;border:1px solid #fecaca;border-radius:10px;
          padding:12px;font-size:13px;color:#991b1b;margin-top:8px}}
  .foot{{background:#f8fafc;padding:14px;text-align:center;color:#94a3b8;
         font-size:11px;border-top:1px solid #e2e8f0}}
</style></head><body>
<div class="w">
  <div class="h">
    <h1>🥋 {nombre_escuela}</h1>
    <p>⚠️ Pago vencido</p>
  </div>
  <div class="b">
    <div class="dias">{dias_atraso}</div>
    <div class="dias-label">días de atraso</div>
    <div class="row"><span>Alumno</span><span>{nombre_alumno}</span></div>
    <div class="row"><span>Concepto</span><span>{concepto}</span></div>
    <div class="row"><span>Venció el</span><span>{fecha_vencimiento}</span></div>
    <div class="monto">${monto:,.0f} MXN</div>
    <div class="alert">
      ⏳ Tienes hasta <strong>5 días hábiles</strong> para regularizar tu pago
      antes de que se tome una acción sobre la inscripción del alumno.
    </div>
  </div>
  <div class="foot">Generado automáticamente · TKW System</div>
</div></body></html>"""


def _html_aviso_baja(
    nombre_alumno: str, nombre_escuela: str,
    concepto: str, monto: float,
    fecha_vencimiento: str, dias_atraso: int,
) -> str:
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:0}}
  .w{{max-width:520px;margin:32px auto;background:#fff;border-radius:20px;
      box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden}}
  .h{{background:#0f172a;padding:28px;text-align:center}}
  .h h1{{color:#fff;margin:0;font-size:20px;font-weight:900}}
  .h p{{color:rgba(255,255,255,.6);margin:6px 0 0;font-size:12px}}
  .b{{padding:24px;text-align:center}}
  .dias{{font-size:64px;font-weight:900;color:#0f172a;line-height:1}}
  .dias-label{{font-size:14px;color:#64748b;margin-bottom:20px}}
  .row{{display:flex;justify-content:space-between;padding:9px 0;
        border-bottom:1px solid #f1f5f9;text-align:left}}
  .row span:first-child{{color:#64748b;font-size:13px}}
  .row span:last-child{{color:#0f172a;font-size:13px;font-weight:700}}
  .monto{{font-size:28px;font-weight:900;color:#0f172a;padding:16px 0}}
  .alert{{background:#0f172a;border-radius:10px;padding:16px;
          font-size:13px;color:#fff;margin-top:8px;line-height:1.6}}
  .foot{{background:#f8fafc;padding:14px;text-align:center;color:#94a3b8;
         font-size:11px;border-top:1px solid #e2e8f0}}
</style></head><body>
<div class="w">
  <div class="h">
    <h1>🥋 {nombre_escuela}</h1>
    <p>🚨 Aviso de suspensión</p>
  </div>
  <div class="b">
    <div class="dias">{dias_atraso}</div>
    <div class="dias-label">días de atraso</div>
    <div class="row"><span>Alumno</span><span>{nombre_alumno}</span></div>
    <div class="row"><span>Concepto</span><span>{concepto}</span></div>
    <div class="row"><span>Venció el</span><span>{fecha_vencimiento}</span></div>
    <div class="monto">${monto:,.0f} MXN</div>
    <div class="alert">
      🚨 <strong>Aviso importante:</strong> El alumno <strong>{nombre_alumno}</strong>
      será dado de baja del dojo si no se regulariza el pago a la brevedad.<br><br>
      Comunícate con la academia para llegar a un acuerdo antes de que
      se proceda con la suspensión.
    </div>
  </div>
  <div class="foot">Generado automáticamente · TKW System</div>
</div></body></html>"""


# ─────────────────────────────────────────────────────────────
#  DÍAS HÁBILES (lunes a viernes, sin festivos)
# ─────────────────────────────────────────────────────────────

FESTIVOS_MX = {
    # Festivos fijos México
    (1,  1),   # Año nuevo
    (2,  5),   # Constitución
    (3,  21),  # Natalicio Juárez
    (5,  1),   # Día del trabajo
    (9,  16),  # Independencia
    (11, 2),   # Día de muertos (opcional)
    (11, 20),  # Revolución
    (12, 25),  # Navidad
}

def dias_habiles_transcurridos(fecha_inicio: date, fecha_fin: date) -> int:
    """Cuenta días hábiles entre dos fechas (lunes-viernes, sin festivos MX)."""
    if fecha_fin <= fecha_inicio:
        return 0
    count = 0
    current = fecha_inicio + timedelta(days=1)
    while current <= fecha_fin:
        if current.weekday() < 5 and (current.month, current.day) not in FESTIVOS_MX:
            count += 1
        current += timedelta(days=1)
    return count


# ─────────────────────────────────────────────────────────────
#  JOB PRINCIPAL — corre cada día a las 9:00 AM
# ─────────────────────────────────────────────────────────────

async def revisar_pagos_y_notificar():
    """
    Revisa todos los pagos pendientes y envía correos según las reglas:
    - 5 días antes del vencimiento: aviso pronto
    - 1-5 días hábiles después: aviso de atraso (diario)
    - 6+ días hábiles después: aviso de baja (diario)
    """
    db  = get_db()
    hoy = date.today()

    print(f"[SCHEDULER] Iniciando revisión de pagos — {hoy}")

    # Traer todos los pagos pendientes con datos del alumno y escuela
    try:
        pagos_res = db.table("pagos").select(
            "idpago, idalumno, idescuela, concepto, monto, fecha_pago, folio_recibo, "
            "alumnos(nombres, apellidopaterno, correotutor, estatus), "
            "datosescuela(nombreescuela)"
        ).eq("estatus", 0).execute()  # 0 = PENDIENTE
    except Exception as e:
        print(f"[SCHEDULER ERROR] No se pudo consultar pagos: {e}")
        return

    pagos = pagos_res.data or []
    print(f"[SCHEDULER] {len(pagos)} pagos pendientes encontrados")

    enviados = 0
    omitidos = 0

    for pago in pagos:
        try:
            alumno  = pago.get("alumnos") or {}
            escuela = pago.get("datosescuela") or {}

            # Saltar si el alumno está dado de baja (estatus != 1)
            if alumno.get("estatus") != 1:
                omitidos += 1
                continue

            correo = alumno.get("correotutor")
            if not correo:
                omitidos += 1
                continue

            nombre_alumno  = f"{alumno.get('nombres','')} {alumno.get('apellidopaterno','')}".strip()
            nombre_escuela = escuela.get("nombreescuela", "Tu Academia")
            concepto       = pago.get("concepto", "Pago pendiente")
            monto          = float(pago.get("monto") or 0)
            folio          = pago.get("folio_recibo", "")

            # Parsear fecha de vencimiento
            fecha_str = str(pago.get("fecha_pago") or "")[:10]
            if not fecha_str or fecha_str == "None":
                omitidos += 1
                continue
            fecha_venc = date.fromisoformat(fecha_str)

            delta = (hoy - fecha_venc).days  # negativo = aún no vence

            # ── CASO 1: 5 días ANTES del vencimiento ─────────────
            if delta == -5:
                ok = send_email(
                    correo,
                    f"⏰ Tu pago vence en 5 días — {concepto} | {nombre_escuela}",
                    _html_aviso_pronto(
                        nombre_alumno, nombre_escuela,
                        concepto, monto, fecha_str, 5,
                    ),
                    nombre_escuela,
                )
                if ok: enviados += 1

            # ── CASO 2: 1-5 días hábiles de atraso ───────────────
            elif delta > 0:
                dias_hab = dias_habiles_transcurridos(fecha_venc, hoy)

                if 1 <= dias_hab <= 5:
                    ok = send_email(
                        correo,
                        f"⚠️ Pago vencido — {dias_hab} días de atraso | {nombre_escuela}",
                        _html_aviso_atraso(
                            nombre_alumno, nombre_escuela,
                            concepto, monto, fecha_str, dias_hab,
                        ),
                        nombre_escuela,
                    )
                    if ok: enviados += 1

                # ── CASO 3: 6+ días hábiles → aviso de baja ──────
                elif dias_hab >= 6:
                    ok = send_email(
                        correo,
                        f"🚨 Aviso de suspensión — {dias_hab} días de atraso | {nombre_escuela}",
                        _html_aviso_baja(
                            nombre_alumno, nombre_escuela,
                            concepto, monto, fecha_str, dias_hab,
                        ),
                        nombre_escuela,
                    )
                    if ok: enviados += 1

        except Exception as e:
            print(f"[SCHEDULER ERROR] Pago {pago.get('idpago')}: {e}")
            continue

    print(f"[SCHEDULER] ✓ Revisión completa — {enviados} correos enviados, {omitidos} omitidos")


# ─────────────────────────────────────────────────────────────
#  INICIAR / DETENER  (llamado desde main.py)
# ─────────────────────────────────────────────────────────────

def start_scheduler():
    """Inicia el scheduler. Llamar en el startup de FastAPI."""
    if not scheduler.running:
        scheduler.add_job(
            revisar_pagos_y_notificar,
            trigger=CronTrigger(hour=9, minute=0),   # 9:00 AM hora México
            id="revisar_pagos",
            replace_existing=True,
            misfire_grace_time=3600,  # Si uvicorn estaba caído, ejecuta hasta 1h después
        )
        scheduler.start()
        print("[SCHEDULER] ✓ Iniciado — corre diario a las 9:00 AM (México)")


def stop_scheduler():
    """Detiene el scheduler. Llamar en el shutdown de FastAPI."""
    if scheduler.running:
        scheduler.shutdown()
        print("[SCHEDULER] Detenido")