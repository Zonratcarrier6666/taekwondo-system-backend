"""
app/routers/examenes.py
────────────────────────────────────────────────────────────────
Módulo de Exámenes de Grado

Endpoints:
  POST   /examenes/                          Crear examen
  GET    /examenes/                          Listar exámenes (Escuela o Profesor)
  GET    /examenes/{idexamen}                Detalle con alumnos inscritos
  PUT    /examenes/{idexamen}                Editar examen (fecha, lugar, sinodal, nombre)
  DELETE /examenes/{idexamen}                Eliminar examen (solo si no tiene historial)
  POST   /examenes/{idexamen}/upload-pdf     Subir PDF del examen al bucket
  POST   /examenes/{idexamen}/inscribir      Inscribir alumnos (lote o individual) + generar pagos
  DELETE /examenes/{idexamen}/alumnos/{id}   Quitar alumno del examen y anular su pago
  POST   /examenes/{idexamen}/calificar      Registrar calificación de un alumno (requiere pago)
  GET    /examenes/{idexamen}/pdf            Redirige a la URL pública del PDF
"""

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from fastapi.responses import RedirectResponse
from typing import List, Optional
from supabase import Client
from datetime import date
import uuid

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.roles import UserRole
from pydantic import BaseModel

router = APIRouter(tags=["Exámenes y Grados"])

# ─────────────────────────────────────────────────────────────
#  CONSTANTES
# ─────────────────────────────────────────────────────────────

ID_TIPO_PAGO_EXAMEN = 3   # 1=Mensualidad 2=Inscripción 3=Examen 4=Torneo
BUCKET_EXAMENES     = "examenes"   # bucket de Supabase Storage


# ─────────────────────────────────────────────────────────────
#  SCHEMAS
# ─────────────────────────────────────────────────────────────

class ExamenCreate(BaseModel):
    nombre_examen:    str
    fecha_programada: str            # YYYY-MM-DD
    lugar:            Optional[str] = "Dojo Central"
    costo_examen:     Optional[float] = 0.0
    sinodal:          Optional[str] = None

class ExamenUpdate(BaseModel):
    nombre_examen:    Optional[str] = None
    fecha_programada: Optional[str] = None
    lugar:            Optional[str] = None
    costo_examen:     Optional[float] = None
    sinodal:          Optional[str] = None
    estatus:          Optional[int] = None

class InscribirRequest(BaseModel):
    idalumnos: List[int]             # uno o varios

class CalificarRequest(BaseModel):
    idalumno:       int
    calificacion:   float            # ej. 8.5
    idgrado_nuevo:  int              # cinta a la que sube
    notas:          Optional[str] = None
    aprobado:       Optional[bool] = None   # si None, se deriva: cal >= 6.0


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def _get_idescuela_profesor(idusuario: int, db: Client) -> tuple[int, int]:
    res = db.table("profesores").select("idprofesor, idescuela").eq("idusuario", idusuario).execute()
    if not res.data:
        raise HTTPException(404, "Perfil de profesor no encontrado.")
    return res.data[0]["idprofesor"], res.data[0]["idescuela"]

def _get_idescuela_escuela(idusuario: int, db: Client) -> int:
    res = db.table("datosescuela").select("idescuela").eq("idusuario", idusuario).execute()
    if not res.data:
        raise HTTPException(404, "Perfil de escuela no encontrado.")
    return res.data[0]["idescuela"]

def _resolver_rol(current_user: dict, db: Client) -> tuple[str, int, Optional[int]]:
    """Devuelve (rol, idescuela, idprofesor_o_None)."""
    rol       = current_user.get("rol")
    idusuario = current_user.get("idusuario")
    if rol == UserRole.ESCUELA:
        return rol, _get_idescuela_escuela(idusuario, db), None
    if rol == UserRole.PROFESOR:
        idprofesor, idescuela = _get_idescuela_profesor(idusuario, db)
        return rol, idescuela, idprofesor
    raise HTTPException(403, "Sin permisos para este módulo.")

def _validar_examen(idexamen: int, idescuela: int, db: Client) -> dict:
    res = db.table("examenes").select("*").eq("idexamen", idexamen).execute()
    if not res.data:
        raise HTTPException(404, "Examen no encontrado.")
    e = res.data[0]
    if e["idescuela"] != idescuela:
        raise HTTPException(403, "El examen no pertenece a tu escuela.")
    return e

def _enriquecer_examenes(examenes: list, db: Client) -> list:
    """Agrega conteos de inscritos y pagados a cada examen."""
    if not examenes:
        return []
    ids = [e["idexamen"] for e in examenes]

    # Alumnos inscritos: registros en historial_grados vinculados al examen
    hist_res = db.table("historial_grados")\
        .select("idexamen, idalumno, calificacion, aprobado")\
        .in_("idexamen", ids).execute()
    hist_map: dict = {}
    for h in (hist_res.data or []):
        eid = h["idexamen"]
        if eid not in hist_map:
            hist_map[eid] = []
        hist_map[eid].append(h)

    # Pagos pendientes / pagados ligados al examen (concepto contiene el idexamen)
    pagos_res = db.table("pagos")\
        .select("idalumno, idexamen_ref, estatus")\
        .in_("idexamen_ref", ids).execute()
    pagos_map: dict = {}
    for p in (pagos_res.data or []):
        eid = p.get("idexamen_ref")
        if eid not in pagos_map:
            pagos_map[eid] = []
        pagos_map[eid].append(p)

    for e in examenes:
        eid = e["idexamen"]
        inscritos = hist_map.get(eid, [])
        pagos     = pagos_map.get(eid, [])
        e["_inscritos"]   = len(inscritos)
        e["_calificados"] = sum(1 for h in inscritos if h.get("calificacion") is not None)
        e["_pagados"]     = sum(1 for p in pagos if p.get("estatus") == 1)
        e["_pendientes"]  = sum(1 for p in pagos if p.get("estatus") == 0)
    return examenes


# ─────────────────────────────────────────────────────────────
#  CRUD EXAMEN
# ─────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
async def crear_examen(
    body: ExamenCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Crea un examen. Solo Profesor o Escuela."""
    rol, idescuela, idprofesor = _resolver_rol(current_user, db)

    # Validar fecha
    try:
        date.fromisoformat(body.fecha_programada)
    except ValueError:
        raise HTTPException(400, "Fecha inválida. Usa YYYY-MM-DD.")

    row = {
        "idescuela":        idescuela,
        "nombre_examen":    body.nombre_examen.strip(),
        "fecha_programada": body.fecha_programada,
        "lugar":            body.lugar or "Dojo Central",
        "costo_examen":     body.costo_examen or 0.0,
        "sinodal":          body.sinodal,
        "idprofesor":       idprofesor,
        "estatus":          1,
    }
    res = db.table("examenes").insert(row).execute()
    return res.data[0]


@router.get("/")
async def listar_examenes(
    estatus: Optional[int] = Query(None, description="1=activo, 0=inactivo"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Lista exámenes. Profesor ve solo los suyos. Escuela ve todos."""
    rol, idescuela, idprofesor = _resolver_rol(current_user, db)

    q = db.table("examenes").select("*").eq("idescuela", idescuela).order("fecha_programada", desc=True)

    if rol == UserRole.PROFESOR and idprofesor:
        q = q.eq("idprofesor", idprofesor)
    if estatus is not None:
        q = q.eq("estatus", estatus)

    res = q.execute()
    return _enriquecer_examenes(res.data or [], db)


@router.get("/{idexamen}")
async def detalle_examen(
    idexamen: int,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Detalle del examen con lista de alumnos inscritos y su estatus de pago."""
    _, idescuela, _ = _resolver_rol(current_user, db)
    examen = _validar_examen(idexamen, idescuela, db)

    # Alumnos inscritos con calificación
    hist_res = db.table("historial_grados")\
        .select(
            "idhistorial, idalumno, idgrado_anterior, idgrado_nuevo, "
            "calificacion, aprobado, notas, fecharegistro, "
            "alumnos(nombres, apellidopaterno, fotoalumno), "
            "grado_ant:cintasgrados!idgrado_anterior(nivelkupdan, color, color_stripe), "
            "grado_nvo:cintasgrados!idgrado_nuevo(nivelkupdan, color, color_stripe)"
        )\
        .eq("idexamen", idexamen).execute()

    # Pagos de este examen
    pagos_res = db.table("pagos")\
        .select("idpago, idalumno, monto, estatus, metodo_pago")\
        .eq("idexamen_ref", idexamen).execute()
    pagos_map = {p["idalumno"]: p for p in (pagos_res.data or [])}

    alumnos_detalle = []
    for h in (hist_res.data or []):
        pago = pagos_map.get(h["idalumno"])
        alumnos_detalle.append({
            **h,
            "pago": pago,
            "pago_estatus": pago["estatus"] if pago else None,   # 0=pendiente 1=pagado
        })

    examen["alumnos"] = alumnos_detalle
    return examen


@router.put("/{idexamen}")
async def editar_examen(
    idexamen: int,
    body: ExamenUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    rol, idescuela, idprofesor = _resolver_rol(current_user, db)
    examen = _validar_examen(idexamen, idescuela, db)

    # Profesor solo puede editar sus propios exámenes
    if rol == UserRole.PROFESOR and examen.get("idprofesor") != idprofesor:
        raise HTTPException(403, "Solo puedes editar tus propios exámenes.")

    update = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not update:
        raise HTTPException(400, "Nada que actualizar.")

    res = db.table("examenes").update(update).eq("idexamen", idexamen).execute()
    return res.data[0]


@router.delete("/{idexamen}", status_code=204)
async def eliminar_examen(
    idexamen: int,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    rol, idescuela, idprofesor = _resolver_rol(current_user, db)
    examen = _validar_examen(idexamen, idescuela, db)

    if rol == UserRole.PROFESOR and examen.get("idprofesor") != idprofesor:
        raise HTTPException(403, "Solo puedes eliminar tus propios exámenes.")

    # Bloquear si ya hay calificaciones registradas
    hist = db.table("historial_grados").select("idhistorial", count="exact")\
        .eq("idexamen", idexamen)\
        .not_.is_("calificacion", "null").execute()
    if (hist.count or 0) > 0:
        raise HTTPException(400, f"No se puede eliminar: hay {hist.count} calificación(es) registrada(s).")

    # Anular pagos pendientes asociados
    db.table("pagos").update({"estatus": 2})\
        .eq("idexamen_ref", idexamen).eq("estatus", 0).execute()

    db.table("examenes").delete().eq("idexamen", idexamen).execute()
    return None


# ─────────────────────────────────────────────────────────────
#  SUBIR PDF
# ─────────────────────────────────────────────────────────────

@router.post("/{idexamen}/upload-pdf")
async def subir_pdf_examen(
    idexamen: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Sube el PDF del examen al bucket 'examenes'."""
    rol, idescuela, idprofesor = _resolver_rol(current_user, db)
    examen = _validar_examen(idexamen, idescuela, db)

    if rol == UserRole.PROFESOR and examen.get("idprofesor") != idprofesor:
        raise HTTPException(403, "Solo puedes subir archivos a tus propios exámenes.")

    extension = (file.filename or "").split(".")[-1].lower()
    if extension != "pdf":
        raise HTTPException(400, "Solo se permiten archivos PDF.")

    file_path = f"examen_{idexamen}_{uuid.uuid4().hex[:8]}.pdf"
    file_content = await file.read()

    try:
        db.storage.from_(BUCKET_EXAMENES).upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": "application/pdf"},
        )
        pdf_url = db.storage.from_(BUCKET_EXAMENES).get_public_url(file_path)
        res = db.table("examenes").update({"archivo_pdf": pdf_url})\
            .eq("idexamen", idexamen).execute()
        return {"ok": True, "archivo_pdf": pdf_url, "examen": res.data[0]}
    except Exception as e:
        raise HTTPException(500, f"Error al subir el PDF: {str(e)}")


@router.get("/{idexamen}/pdf")
async def descargar_pdf_examen(
    idexamen: int,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Redirige a la URL pública del PDF del examen."""
    _, idescuela, _ = _resolver_rol(current_user, db)
    examen = _validar_examen(idexamen, idescuela, db)

    if not examen.get("archivo_pdf"):
        raise HTTPException(404, "Este examen aún no tiene PDF cargado.")
    return RedirectResponse(url=examen["archivo_pdf"])


# ─────────────────────────────────────────────────────────────
#  INSCRIBIR ALUMNOS
# ─────────────────────────────────────────────────────────────

@router.post("/{idexamen}/inscribir")
async def inscribir_alumnos(
    idexamen: int,
    body: InscribirRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Inscribe uno o varios alumnos al examen y genera un pago pendiente
    por el costo del examen para cada uno.
    Idempotente: si el alumno ya está inscrito, lo omite.
    """
    rol, idescuela, idprofesor = _resolver_rol(current_user, db)
    examen = _validar_examen(idexamen, idescuela, db)

    if not body.idalumnos:
        raise HTTPException(400, "Lista de alumnos vacía.")

    # Validar que los alumnos pertenecen a la escuela
    alumnos_res = db.table("alumnos")\
        .select("idalumno, nombres, apellidopaterno, idgradoactual, idescuela")\
        .in_("idalumno", body.idalumnos).execute()

    alumnos_validos = [a for a in (alumnos_res.data or []) if a["idescuela"] == idescuela]
    if not alumnos_validos:
        raise HTTPException(400, "Ningún alumno válido para esta escuela.")

    # Ver quiénes ya están inscritos
    ya_inscritos_res = db.table("historial_grados")\
        .select("idalumno").eq("idexamen", idexamen).execute()
    ya_inscritos = {h["idalumno"] for h in (ya_inscritos_res.data or [])}

    costo = float(examen.get("costo_examen") or 0)
    nuevos = []
    pagos_nuevos = []

    for alumno in alumnos_validos:
        aid = alumno["idalumno"]
        if aid in ya_inscritos:
            continue

        # Crear registro en historial_grados (sin calificación aún)
        nuevos.append({
            "idalumno":            aid,
            "idgrado_anterior":    alumno["idgradoactual"],
            "idgrado_nuevo":       alumno["idgradoactual"],  # se actualiza al calificar
            "fecha_examen":        examen["fecha_programada"],
            "idprofesor_evaluador": idprofesor,
            "idexamen":            idexamen,
            "notas":               None,
        })

        # Generar pago pendiente si el examen tiene costo
        if costo > 0:
            pagos_nuevos.append({
                "idalumno":      aid,
                "idescuela":     idescuela,
                "concepto":      f"Examen: {examen['nombre_examen']}",
                "monto":         costo,
                "estatus":       0,              # pendiente
                "id_tipo_pago":  ID_TIPO_PAGO_EXAMEN,
                "idexamen_ref":  idexamen,
            })

    if nuevos:
        db.table("historial_grados").insert(nuevos).execute()
    if pagos_nuevos:
        db.table("pagos").insert(pagos_nuevos).execute()

    return {
        "ok":           True,
        "inscritos":    len(nuevos),
        "ya_estaban":   len(alumnos_validos) - len(nuevos),
        "pagos_generados": len(pagos_nuevos),
        "mensaje": f"{len(nuevos)} alumno(s) inscritos. {len(pagos_nuevos)} pago(s) generado(s).",
    }


@router.delete("/{idexamen}/alumnos/{idalumno}", status_code=200)
async def quitar_alumno_examen(
    idexamen: int,
    idalumno: int,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Quita un alumno del examen y anula su pago pendiente."""
    rol, idescuela, idprofesor = _resolver_rol(current_user, db)
    _validar_examen(idexamen, idescuela, db)

    # Verificar que no tenga calificación ya registrada
    hist = db.table("historial_grados").select("idhistorial, calificacion")\
        .eq("idexamen", idexamen).eq("idalumno", idalumno).execute()
    if not hist.data:
        raise HTTPException(404, "El alumno no está inscrito en este examen.")
    if hist.data[0].get("calificacion") is not None:
        raise HTTPException(400, "No se puede quitar al alumno: ya tiene calificación registrada.")

    db.table("historial_grados").delete()\
        .eq("idexamen", idexamen).eq("idalumno", idalumno).execute()

    # Anular pago pendiente
    db.table("pagos").update({"estatus": 2})\
        .eq("idexamen_ref", idexamen).eq("idalumno", idalumno).eq("estatus", 0).execute()

    return {"ok": True, "mensaje": "Alumno quitado del examen y pago anulado."}


# ─────────────────────────────────────────────────────────────
#  CALIFICAR
# ─────────────────────────────────────────────────────────────

@router.post("/{idexamen}/calificar")
async def calificar_alumno(
    idexamen: int,
    body: CalificarRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Registra la calificación de un alumno.
    BLOQUEA si el pago del examen está pendiente (estatus=0).
    Si aprueba (cal >= 6.0 por defecto), actualiza su grado actual.
    """
    rol, idescuela, idprofesor = _resolver_rol(current_user, db)
    _validar_examen(idexamen, idescuela, db)

    # Verificar que el alumno está inscrito
    hist_res = db.table("historial_grados").select("*")\
        .eq("idexamen", idexamen).eq("idalumno", body.idalumno).execute()
    if not hist_res.data:
        raise HTTPException(404, "El alumno no está inscrito en este examen.")
    hist = hist_res.data[0]

    # ── BLOQUEO PRINCIPAL: verificar pago ────────────────────
    pago_res = db.table("pagos").select("idpago, estatus")\
        .eq("idexamen_ref", idexamen).eq("idalumno", body.idalumno).execute()

    if pago_res.data:
        pago = pago_res.data[0]
        if pago["estatus"] == 0:
            raise HTTPException(
                400,
                "No se puede registrar la calificación: el alumno tiene el pago del examen pendiente."
            )
    # Si no hay pago (examen sin costo), se permite pasar

    # Validar calificación
    if not (0 <= body.calificacion <= 10):
        raise HTTPException(400, "La calificación debe estar entre 0 y 10.")

    aprobado = body.aprobado if body.aprobado is not None else (body.calificacion >= 6.0)

    # Actualizar historial
    update_hist = {
        "calificacion":  body.calificacion,
        "aprobado":      aprobado,
        "idgrado_nuevo": body.idgrado_nuevo,
        "notas":         body.notas,
    }
    # Validar que grado_nuevo != grado_anterior si aprobó
    if aprobado and body.idgrado_nuevo == hist["idgrado_anterior"]:
        raise HTTPException(400, "El grado nuevo debe ser diferente al grado anterior cuando el alumno aprueba.")

    db.table("historial_grados").update(update_hist)\
        .eq("idhistorial", hist["idhistorial"]).execute()

    # Si aprobó → actualizar grado actual del alumno
    if aprobado:
        db.table("alumnos").update({"idgradoactual": body.idgrado_nuevo})\
            .eq("idalumno", body.idalumno).execute()

    return {
        "ok":          True,
        "idalumno":    body.idalumno,
        "calificacion": body.calificacion,
        "aprobado":    aprobado,
        "grado_nuevo": body.idgrado_nuevo if aprobado else None,
        "mensaje": "Calificación registrada." + (" Grado actualizado." if aprobado else " Alumno reprobado."),
    }