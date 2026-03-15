"""
app/routers/asistencia.py
─────────────────────────────────────────────────────────────
Módulo de pase de lista diario.

Endpoints disponibles:
  GET  /asistencia/hoy                    → alumnos del día con estatus (Escuela o Profesor)
  POST /asistencia/pasar-lista            → registra/actualiza lista completa del día
  GET  /asistencia/historial/{idalumno}   → historial de un alumno (Escuela o Profesor)
  GET  /asistencia/resumen                → % asistencia del grupo por rango de fechas
  GET  /asistencia/fecha/{fecha}          → lista de un día específico (YYYY-MM-DD)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from supabase import Client
from datetime import date, timedelta

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.roles import UserRole
from pydantic import BaseModel

router = APIRouter(tags=["Asistencia y Control"])


# ─────────────────────────────────────────────────────────────
#  SCHEMAS
# ─────────────────────────────────────────────────────────────

class RegistroAsistencia(BaseModel):
    idalumno: int
    presente: bool = True

class PaseListaRequest(BaseModel):
    fecha: Optional[str] = None   # YYYY-MM-DD, default = hoy
    registros: List[RegistroAsistencia]

class AlumnoDiaResponse(BaseModel):
    idalumno: int
    nombres: str
    apellidopaterno: str
    foto: Optional[str] = None
    cinta_color: Optional[str] = None
    cinta_nivel: Optional[str] = None
    presente: Optional[bool] = None   # None = no registrado aún hoy
    id_asistencia: Optional[int] = None


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def _get_idescuela(idusuario: int, db: Client) -> int:
    res = db.table("datosescuela").select("idescuela").eq("idusuario", idusuario).execute()
    if not res.data:
        raise HTTPException(404, "Perfil de escuela no encontrado.")
    return res.data[0]["idescuela"]

def _get_idprofesor_y_escuela(idusuario: int, db: Client) -> tuple[int, int]:
    res = db.table("profesores").select("idprofesor, idescuela").eq("idusuario", idusuario).execute()
    if not res.data:
        raise HTTPException(404, "Perfil de profesor no encontrado.")
    return res.data[0]["idprofesor"], res.data[0]["idescuela"]

def _get_alumnos_activos(idescuela: int, idprofesor: Optional[int], db: Client) -> list:
    """Devuelve alumnos activos de la escuela, opcionalmente filtrados por profesor."""
    q = (
        db.table("alumnos")
        .select(
            "idalumno, nombres, apellidopaterno, fotoalumno, "
            "cintasgrados(nivelkupdan, color)"
        )
        .eq("idescuela", idescuela)
        .eq("estatus", 1)
    )
    if idprofesor is not None:
        q = q.eq("idprofesor", idprofesor)
    res = q.order("apellidopaterno").execute()
    return res.data or []


# ─────────────────────────────────────────────────────────────
#  GET /asistencia/hoy
#  Alumnos del grupo con su estatus de asistencia de hoy
# ─────────────────────────────────────────────────────────────

@router.get("/hoy", response_model=List[AlumnoDiaResponse])
async def lista_hoy(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Devuelve todos los alumnos activos del grupo con su estatus de hoy.
    - Si `presente` es None → aún no se pasó lista para ese alumno.
    - Accesible para roles Escuela y Profesor.
    """
    rol = current_user.get("rol")
    idusuario = current_user.get("idusuario")
    hoy = str(date.today())

    if rol == UserRole.ESCUELA:
        idescuela = _get_idescuela(idusuario, db)
        idprofesor = None
    elif rol == UserRole.PROFESOR:
        idprofesor, idescuela = _get_idprofesor_y_escuela(idusuario, db)
    else:
        raise HTTPException(403, "Sin permisos para esta acción.")

    alumnos = _get_alumnos_activos(idescuela, idprofesor if rol == UserRole.PROFESOR else None, db)

    if not alumnos:
        return []

    ids = [a["idalumno"] for a in alumnos]

    # Asistencias de hoy
    asist_res = (
        db.table("asistencia")
        .select("id, idalumno, presente")
        .eq("fecha", hoy)
        .in_("idalumno", ids)
        .execute()
    )
    asist_map = {r["idalumno"]: r for r in (asist_res.data or [])}

    result = []
    for a in alumnos:
        cinta = a.get("cintasgrados") or {}
        reg   = asist_map.get(a["idalumno"])
        result.append(AlumnoDiaResponse(
            idalumno       = a["idalumno"],
            nombres        = a["nombres"],
            apellidopaterno= a["apellidopaterno"],
            foto           = a.get("fotoalumno"),
            cinta_color    = cinta.get("color"),
            cinta_nivel    = cinta.get("nivelkupdan"),
            presente       = reg["presente"] if reg else None,
            id_asistencia  = reg["id"] if reg else None,
        ))

    return result


# ─────────────────────────────────────────────────────────────
#  POST /asistencia/pasar-lista
#  Registra o actualiza la asistencia del día completo
# ─────────────────────────────────────────────────────────────

@router.post("/pasar-lista", status_code=200)
async def pasar_lista(
    body: PaseListaRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Registra o actualiza la asistencia de una lista de alumnos para una fecha.
    - Usa UPSERT con la constraint `unique_asistencia_dia (idalumno, fecha)`.
    - Si no se pasa `fecha`, usa el día de hoy.
    - Accesible para roles Escuela y Profesor.
    """
    rol      = current_user.get("rol")
    idusuario = current_user.get("idusuario")

    if rol == UserRole.ESCUELA:
        idescuela = _get_idescuela(idusuario, db)
    elif rol == UserRole.PROFESOR:
        _, idescuela = _get_idprofesor_y_escuela(idusuario, db)
    else:
        raise HTTPException(403, "Sin permisos para esta acción.")

    fecha = body.fecha or str(date.today())

    # Validar formato de fecha
    try:
        date.fromisoformat(fecha)
    except ValueError:
        raise HTTPException(400, "Formato de fecha inválido. Usa YYYY-MM-DD.")

    if not body.registros:
        raise HTTPException(400, "La lista de registros está vacía.")

    # Construir upsert
    rows = [
        {
            "idalumno":  r.idalumno,
            "idescuela": idescuela,
            "fecha":     fecha,
            "presente":  r.presente,
        }
        for r in body.registros
    ]

    try:
        db.table("asistencia").upsert(
            rows,
            on_conflict="idalumno,fecha"
        ).execute()
    except Exception as e:
        raise HTTPException(500, f"Error al guardar asistencia: {str(e)}")

    presentes = sum(1 for r in body.registros if r.presente)
    ausentes  = len(body.registros) - presentes

    return {
        "ok":        True,
        "fecha":     fecha,
        "total":     len(body.registros),
        "presentes": presentes,
        "ausentes":  ausentes,
        "mensaje":   f"Lista guardada: {presentes} presentes, {ausentes} ausentes.",
    }


# ─────────────────────────────────────────────────────────────
#  GET /asistencia/fecha/{fecha}
#  Lista de un día específico
# ─────────────────────────────────────────────────────────────

@router.get("/fecha/{fecha}", response_model=List[AlumnoDiaResponse])
async def lista_por_fecha(
    fecha: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Igual que /hoy pero para una fecha específica (YYYY-MM-DD).
    """
    try:
        date.fromisoformat(fecha)
    except ValueError:
        raise HTTPException(400, "Formato de fecha inválido. Usa YYYY-MM-DD.")

    rol      = current_user.get("rol")
    idusuario = current_user.get("idusuario")

    if rol == UserRole.ESCUELA:
        idescuela  = _get_idescuela(idusuario, db)
        idprofesor = None
    elif rol == UserRole.PROFESOR:
        idprofesor, idescuela = _get_idprofesor_y_escuela(idusuario, db)
    else:
        raise HTTPException(403, "Sin permisos para esta acción.")

    alumnos = _get_alumnos_activos(idescuela, idprofesor if rol == UserRole.PROFESOR else None, db)
    if not alumnos:
        return []

    ids = [a["idalumno"] for a in alumnos]
    asist_res = (
        db.table("asistencia")
        .select("id, idalumno, presente")
        .eq("fecha", fecha)
        .in_("idalumno", ids)
        .execute()
    )
    asist_map = {r["idalumno"]: r for r in (asist_res.data or [])}

    result = []
    for a in alumnos:
        cinta = a.get("cintasgrados") or {}
        reg   = asist_map.get(a["idalumno"])
        result.append(AlumnoDiaResponse(
            idalumno        = a["idalumno"],
            nombres         = a["nombres"],
            apellidopaterno = a["apellidopaterno"],
            foto            = a.get("fotoalumno"),
            cinta_color     = cinta.get("color"),
            cinta_nivel     = cinta.get("nivelkupdan"),
            presente        = reg["presente"] if reg else None,
            id_asistencia   = reg["id"] if reg else None,
        ))

    return result


# ─────────────────────────────────────────────────────────────
#  GET /asistencia/historial/{idalumno}
#  Historial de asistencia de un alumno
# ─────────────────────────────────────────────────────────────

@router.get("/historial/{idalumno}")
async def historial_alumno(
    idalumno: int,
    desde: Optional[str] = Query(None, description="Fecha inicio YYYY-MM-DD"),
    hasta: Optional[str] = Query(None, description="Fecha fin YYYY-MM-DD"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Devuelve el historial de asistencia de un alumno con métricas.
    Por defecto muestra los últimos 30 días.
    """
    rol      = current_user.get("rol")
    idusuario = current_user.get("idusuario")

    # Obtener idescuela según rol
    if rol == UserRole.ESCUELA:
        idescuela = _get_idescuela(idusuario, db)
    elif rol == UserRole.PROFESOR:
        _, idescuela = _get_idprofesor_y_escuela(idusuario, db)
    else:
        raise HTTPException(403, "Sin permisos.")

    # Validar que el alumno pertenece a esta escuela
    alumno_res = (
        db.table("alumnos")
        .select("idalumno, nombres, apellidopaterno, idescuela")
        .eq("idalumno", idalumno)
        .execute()
    )
    if not alumno_res.data or alumno_res.data[0]["idescuela"] != idescuela:
        raise HTTPException(403, "El alumno no pertenece a tu escuela.")

    # Rango de fechas
    fecha_hasta = hasta or str(date.today())
    fecha_desde = desde or str(date.today() - timedelta(days=29))

    q = (
        db.table("asistencia")
        .select("id, fecha, presente, fecharegistro")
        .eq("idalumno", idalumno)
        .gte("fecha", fecha_desde)
        .lte("fecha", fecha_hasta)
        .order("fecha", desc=True)
    )
    asist_res = q.execute()
    registros = asist_res.data or []

    total     = len(registros)
    presentes = sum(1 for r in registros if r["presente"])
    ausentes  = total - presentes
    pct       = round((presentes / total * 100), 1) if total > 0 else 0

    alumno = alumno_res.data[0]

    return {
        "alumno": {
            "idalumno":       alumno["idalumno"],
            "nombre_completo": f"{alumno['nombres']} {alumno['apellidopaterno']}",
        },
        "rango": { "desde": fecha_desde, "hasta": fecha_hasta },
        "metricas": {
            "total_dias":  total,
            "presentes":   presentes,
            "ausentes":    ausentes,
            "porcentaje":  pct,
        },
        "registros": registros,
    }


# ─────────────────────────────────────────────────────────────
#  GET /asistencia/resumen
#  Resumen de asistencia del grupo en un rango de fechas
# ─────────────────────────────────────────────────────────────

@router.get("/resumen")
async def resumen_grupo(
    desde: Optional[str] = Query(None, description="Fecha inicio YYYY-MM-DD"),
    hasta: Optional[str] = Query(None, description="Fecha fin YYYY-MM-DD"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Devuelve el porcentaje de asistencia de cada alumno del grupo
    en un rango de fechas. Por defecto: últimos 30 días.
    """
    rol      = current_user.get("rol")
    idusuario = current_user.get("idusuario")

    if rol == UserRole.ESCUELA:
        idescuela  = _get_idescuela(idusuario, db)
        idprofesor = None
    elif rol == UserRole.PROFESOR:
        idprofesor, idescuela = _get_idprofesor_y_escuela(idusuario, db)
    else:
        raise HTTPException(403, "Sin permisos.")

    fecha_hasta = hasta or str(date.today())
    fecha_desde = desde or str(date.today() - timedelta(days=29))

    alumnos = _get_alumnos_activos(
        idescuela,
        idprofesor if rol == UserRole.PROFESOR else None,
        db
    )
    if not alumnos:
        return {"alumnos": [], "rango": {"desde": fecha_desde, "hasta": fecha_hasta}}

    ids = [a["idalumno"] for a in alumnos]

    asist_res = (
        db.table("asistencia")
        .select("idalumno, presente")
        .gte("fecha", fecha_desde)
        .lte("fecha", fecha_hasta)
        .in_("idalumno", ids)
        .execute()
    )
    registros = asist_res.data or []

    # Agrupar por alumno
    from collections import defaultdict
    conteo: dict = defaultdict(lambda: {"total": 0, "presentes": 0})
    for r in registros:
        conteo[r["idalumno"]]["total"]    += 1
        conteo[r["idalumno"]]["presentes"] += int(r["presente"])

    resultado = []
    for a in alumnos:
        aid  = a["idalumno"]
        c    = conteo[aid]
        pct  = round(c["presentes"] / c["total"] * 100, 1) if c["total"] > 0 else None
        cinta = a.get("cintasgrados") or {}
        resultado.append({
            "idalumno":        aid,
            "nombre_completo": f"{a['nombres']} {a['apellidopaterno']}",
            "foto":            a.get("fotoalumno"),
            "cinta_color":     cinta.get("color"),
            "cinta_nivel":     cinta.get("nivelkupdan"),
            "total_dias":      c["total"],
            "presentes":       c["presentes"],
            "ausentes":        c["total"] - c["presentes"],
            "porcentaje":      pct,
        })

    # Ordenar por % de asistencia ascendente (los que más faltan primero)
    resultado.sort(key=lambda x: (x["porcentaje"] is None, x["porcentaje"] or 0))

    return {
        "rango":   {"desde": fecha_desde, "hasta": fecha_hasta},
        "alumnos": resultado,
    }