# ============================================================
#  app/routers/asistencia_torneo.py
#  Logística de entrada y pesaje el día del evento
# ============================================================

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from utils.database   import get_db
from utils.auth_utils import get_current_user
from schemas.torneos import ValidarQR

router = APIRouter(prefix="/asistencia-torneo", tags=["Logística y Check-in"])

# ─── HELPERS ──────────────────────────────────────────────────

def _calcular_edad(fecha_nac: str) -> int:
    from datetime import date
    try:
        fn = date.fromisoformat(str(fecha_nac)[:10])
        hoy = date.today()
        return hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
    except: return 0

# ─── ENDPOINTS ────────────────────────────────────────────────

@router.post("/validar-qr", summary="Check-in oficial vía QR")
async def validar_qr(
    body: ValidarQR,
    db:   Client = Depends(get_db),
):
    """
    Endpoint principal para el staff con smartphone.
    Valida el pago, marca la asistencia y devuelve perfil del alumno.
    """
    # Consulta extendida para mostrar información útil al staff en el momento del escaneo
    r = db.table("inscripciones_torneo").select(
        "*, alumnos(nombres, apellidopaterno, fechanacimiento, peso, idescuela), "
        "datosescuela!inscripciones_torneo_idescuela_fkey(nombreescuela)"
    ).eq("token_qr", body.token).execute()

    if not r.data:
        raise HTTPException(404, "El código QR no pertenece a ningún alumno registrado.")

    insc   = r.data[0]
    al     = insc.get("alumnos") or {}
    esc    = insc.get("datosescuela") or {}
    nombre = f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip()

    # 1. Validar que el pago esté liquidado
    if str(insc.get("estatus_pago")).lower() != "pagado":
        return {
            "ok": False,
            "error": "PAGO_PENDIENTE",
            "mensaje": f"⚠️ ATENCIÓN: El alumno {nombre} tiene un pago pendiente.",
            "alumno": nombre
        }

    # 2. Validar si ya entró (evitar duplicidad/fraude)
    if insc.get("qr_usado"):
        return {
            "ok": False,
            "error": "YA_INGRESADO",
            "mensaje": f"Este pase ya fue escaneado hoy a las {insc.get('hora_llegada')[:16]}.",
            "alumno": nombre
        }

    # 3. Registrar entrada exitosa
    ahora = datetime.now().isoformat()
    db.table("inscripciones_torneo").update({
        "qr_usado":       True,
        "hora_llegada":   ahora,
        "estatus_checkin": True,
        "asistio":         True
    }).eq("idinscripcion", insc["idinscripcion"]).execute()

    return {
        "ok":           True,
        "mensaje":      "✅ Acceso concedido.",
        "alumno":       nombre,
        "escuela":      esc.get("nombreescuela", "Escuela Externa"),
        "edad_real":    _calcular_edad(al.get("fechanacimiento", "")),
        "peso_inscrito": insc.get("peso_declarado"),
        "hora_entrada": ahora
    }

@router.get("/{idtorneo}/reporte-asistencia", summary="Lista de presentes vs ausentes")
async def reporte_asistencia(
    idtorneo: int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db)
):
    """Muestra el conteo en tiempo real de quiénes han llegado al gimnasio."""
    r = db.table("inscripciones_torneo").select(
        "idinscripcion, idalumno, qr_usado, hora_llegada, peso_declarado, "
        "alumnos(nombres, apellidopaterno, idescuela), "
        "datosescuela!inscripciones_torneo_idescuela_fkey(nombreescuela)"
    ).eq("idtorneo", idtorneo).execute()

    presentes = [x for x in r.data if x['qr_usado']]
    ausentes  = [x for x in r.data if not x['qr_usado']]

    return {
        "ok": True,
        "resumen": {
            "total_inscritos": len(r.data),
            "confirmados": len(presentes),
            "pendientes": len(ausentes),
            "porcentaje_asistencia": f"{(len(presentes)/len(r.data)*100 if r.data else 0):.1f}%"
        },
        "lista_presentes": presentes,
        "lista_ausentes": ausentes
    }

@router.post("/checkin-manual/{idinscripcion}", summary="Check-in manual (sin QR)")
async def checkin_manual(
    idinscripcion: int,
    notas: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Permite al administrador marcar asistencia si el QR falla o el alumno no trae celular."""
    if user.get("rol") not in ["SuperAdmin", "Escuela"]:
        raise HTTPException(403, "No tienes permiso para sobreescribir la asistencia.")
        
    db.table("inscripciones_torneo").update({
        "qr_usado": True,
        "hora_llegada": datetime.now().isoformat(),
        "estatus_checkin": True,
        "asistio": True
    }).eq("idinscripcion", idinscripcion).execute()
    
    return {"ok": True, "mensaje": "Asistencia marcada manualmente por el administrador."}