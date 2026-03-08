# ============================================================
#  app/routers/torneos.py
# ============================================================

import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from supabase import Client

from utils.database   import get_db
from utils.auth_utils import get_current_user
from schemas.torneos import (
    CrearTorneo, EditarTorneo,
    InscribirAlumno, InscribirAlumnosLote, InscribirAlumnosConPeso,
    ValidarQR, GenerarMatchmaking,
    EstatusTorneo, EstatusInscripcion, GeneroFiltro,
)
from utils.qr_generator import (
    generar_token_qr, generar_pdf_qr, enviar_qr_por_correo,
)
from utils.matchmaking import generar_matchmaking, resumen_matchmaking

router = APIRouter(tags=["Torneos y Competencias"])


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def _require_roles(user: dict, roles: list):
    if user.get("rol") not in roles:
        raise HTTPException(403, "Sin acceso para esta operación")

def _get_idescuela(user: dict, db: Client) -> int:
    rol = user.get("rol")
    uid = user.get("idusuario")
    if rol == "Escuela":
        r = db.table("datosescuela").select("idescuela").eq("idusuario", uid).execute()
    elif rol == "Profesor":
        r = db.table("profesores").select("idescuela").eq("idusuario", uid).execute()
    else:
        return 0
    if not r.data:
        raise HTTPException(403, "Sin escuela asignada")
    return r.data[0]["idescuela"]

def _calcular_edad(fecha_nac: str) -> int:
    try:
        fn = date.fromisoformat(str(fecha_nac)[:10])
        hoy = date.today()
        return hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
    except:
        return 0

def _folio_torneo() -> str:
    return f"TKW-T-{uuid.uuid4().hex[:8].upper()}"


# ─────────────────────────────────────────────────────────────
#  1. CRUD TORNEOS (SuperAdmin)
# ─────────────────────────────────────────────────────────────

@router.post("/crear", summary="Crear torneo")
async def crear_torneo(
    body: CrearTorneo,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["SuperAdmin"])

    torneo = {
        "nombre":             body.nombre,
        "fecha":              body.fecha,
        "hora_inicio":        body.hora_inicio,
        "sede":               body.sede,
        "ciudad":             body.ciudad,
        "monto_inscripcion":  body.monto_inscripcion,
        "costo_inscripcion":  body.costo_inscripcion,
        "cinta_minima":       body.cinta_minima,
        "cinta_maxima":       body.cinta_maxima,
        "edad_minima":        body.edad_minima,
        "edad_maxima":        body.edad_maxima,
        "peso_minimo":        body.peso_minimo,
        "peso_maximo":        body.peso_maximo,
        "genero":             body.genero if isinstance(body.genero, str) else body.genero.value,
        "descripcion":        body.descripcion,
        "max_participantes":  body.max_participantes,
        "tipo_torneo":        body.tipo_torneo,          # ← NUEVO
        "num_areas":          body.num_areas,            # ← NUEVO
        "max_combates_por_competidor": body.max_combates_por_competidor,  # ← NUEVO
        "estatus":            1,
        "creado_por":         user.get("idusuario"),
    }

    try:
        r = db.table("torneos").insert(torneo).execute()
        if not r.data:
            raise HTTPException(status_code=500, detail="No se pudo crear el torneo.")

        torneo_creado = r.data[0]
        idtorneo = torneo_creado["idtorneo"]

        # ─── NUEVO: Insertar categorías si vienen en el body ─────────
        categorias_creadas = []
        if body.categorias:
            for i, cat in enumerate(body.categorias):
                cat_row = {
                    "idtorneo":         idtorneo,
                    "nombre_categoria": cat.nombre_categoria,
                    "edad_min":         cat.edad_min,
                    "edad_max":         cat.edad_max,
                    "peso_min":         cat.peso_min,
                    "peso_max":         cat.peso_max,
                    "genero":           cat.genero,
                    "grados_permitidos": cat.grados_permitidos,
                    "orden_ejecucion":  cat.orden_ejecucion or (i + 1),
                    "estatus":          "pendiente",
                    "total_inscritos":  0,
                    "bracket_generado": False,
                }
                cat_res = db.table("torneo_categorias").insert(cat_row).execute()
                if cat_res.data:
                    categorias_creadas.append(cat_res.data[0])
        # ─────────────────────────────────────────────────────────────

        return {
            "ok":         True,
            "torneo":     torneo_creado,
            "categorias": categorias_creadas,          # ← devuelve las categorías creadas
            "total_categorias": len(categorias_creadas),
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error al insertar torneo: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{idtorneo}", summary="Editar torneo")
async def editar_torneo(
    idtorneo: int,
    body: EditarTorneo,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["SuperAdmin"])
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if "genero" in upd and hasattr(upd["genero"], "value"):
        upd["genero"] = upd["genero"].value
    if "estatus" in upd and hasattr(upd["estatus"], "value"):
        upd["estatus"] = upd["estatus"].value
    r = db.table("torneos").update(upd).eq("idtorneo", idtorneo).execute()
    return {"ok": True, "torneo": r.data[0] if r.data else upd}


@router.get("/lista", summary="Listar torneos")
async def listar_torneos(
    estatus: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    q = db.table("torneos").select("*").order("fecha", desc=True)
    if estatus:
        q = q.eq("estatus", estatus)
    r = q.execute()
    return {"ok": True, "total": len(r.data), "torneos": r.data}


@router.get("/{idtorneo}", summary="Detalle de un torneo")
async def detalle_torneo(
    idtorneo: int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    r = db.table("torneos").select("*").eq("idtorneo", idtorneo).execute()
    if not r.data:
        raise HTTPException(404, "Torneo no encontrado")

    # Contar inscritos
    inscritos = db.table("inscripciones_torneo").select("idinscripcion")\
        .eq("idtorneo", idtorneo).neq("estatus_pago", "cancelado").execute()

    torneo = r.data[0]
    torneo["total_inscritos"] = len(inscritos.data)
    return {"ok": True, "torneo": torneo}


# ─────────────────────────────────────────────────────────────
#  2. ALUMNOS ELEGIBLES
# ─────────────────────────────────────────────────────────────

@router.get("/{idtorneo}/alumnos-elegibles", summary="Ver alumnos de mi escuela que cumplen requisitos")
async def alumnos_elegibles(
    idtorneo: int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["Escuela", "Profesor", "SuperAdmin"])

    # Obtener torneo
    t_res = db.table("torneos").select("*").eq("idtorneo", idtorneo).execute()
    if not t_res.data:
        raise HTTPException(404, "Torneo no encontrado")
    torneo = t_res.data[0]

    # Obtener idescuela del usuario
    idescuela = _get_idescuela(user, db)

    # Traer alumnos activos de la escuela con su cinta actual
    q = db.table("alumnos").select(
        "idalumno, nombres, apellidopaterno, fechanacimiento, "
        "cintasgrados(idgrado, nivelkupdan, color)"
    ).eq("estatus", 1)

    if idescuela:
        q = q.eq("idescuela", idescuela)

    alumnos_res = q.execute()

    # Obtener ya inscritos en este torneo
    ya_inscritos_res = db.table("inscripciones_torneo").select("idalumno")\
        .eq("idtorneo", idtorneo).neq("estatus_pago", "cancelado").execute()
    ya_inscritos = {r["idalumno"] for r in ya_inscritos_res.data}

    elegibles = []
    no_elegibles = []

    for al in alumnos_res.data:
        edad = _calcular_edad(al.get("fechanacimiento", ""))
        cinta_data = al.get("cintasgrados") or {}
        idcinta = cinta_data.get("idgrado", 0)

        razones = []

        # Verificar requisitos
        if torneo.get("cinta_minima") and idcinta < torneo["cinta_minima"]:
            razones.append("Cinta insuficiente")
        if torneo.get("cinta_maxima") and idcinta > torneo["cinta_maxima"]:
            razones.append("Cinta superior al límite")
        if torneo.get("edad_minima") and edad < torneo["edad_minima"]:
            razones.append(f"Menor de {torneo['edad_minima']} años")
        if torneo.get("edad_maxima") and edad > torneo["edad_maxima"]:
            razones.append(f"Mayor de {torneo['edad_maxima']} años")
        # peso: se valida con peso_declarado al momento de inscribir
        # genero: campo no disponible en alumnos actualmente

        alumno_fmt = {
            "idalumno":        al["idalumno"],
            "nombres":         al["nombres"],
            "apellidopaterno": al["apellidopaterno"],
            "edad":            edad,
            "cinta":           cinta_data.get("nivelkupdan", "Sin cinta"),
            "color_cinta":     cinta_data.get("color", "#888"),
            "peso":            None,
            "genero":          None,
            "ya_inscrito":     al["idalumno"] in ya_inscritos,
        }

        if not razones:
            elegibles.append(alumno_fmt)
        else:
            alumno_fmt["razones_no_elegible"] = razones
            no_elegibles.append(alumno_fmt)

    return {
        "ok":           True,
        "idtorneo":     idtorneo,
        "elegibles":    elegibles,
        "no_elegibles": no_elegibles,
        "total_elegibles": len(elegibles),
    }


# ─────────────────────────────────────────────────────────────
#  3. INSCRIBIR ALUMNOS
# ─────────────────────────────────────────────────────────────

async def _inscribir_uno(
    idtorneo: int, idalumno: int, peso_actual: Optional[float],
    idescuela_usuario: int, user: dict, db: Client,
) -> dict:
    """Inscribe un alumno al torneo y genera el pago pendiente."""

    # Verificar que el alumno pertenece a la escuela del usuario
    al_res = db.table("alumnos").select(
        "idalumno, nombres, apellidopaterno, fechanacimiento, "
        "correotutor, idescuela, cintasgrados(idgrado, color)"
    ).eq("idalumno", idalumno).eq("estatus", 1).execute()

    if not al_res.data:
        return {"idalumno": idalumno, "ok": False, "error": "Alumno no encontrado o inactivo"}

    al = al_res.data[0]

    if idescuela_usuario and al["idescuela"] != idescuela_usuario:
        return {"idalumno": idalumno, "ok": False, "error": "El alumno no pertenece a tu escuela"}

    # Verificar que no esté ya inscrito
    ya = db.table("inscripciones_torneo").select("idinscripcion")\
        .eq("idtorneo", idtorneo).eq("idalumno", idalumno)\
        .neq("estatus_pago", "cancelado").execute()
    if ya.data:
        return {"idalumno": idalumno, "ok": False, "error": "Alumno ya inscrito en este torneo"}

    # Obtener datos del torneo
    t_res = db.table("torneos").select("*").eq("idtorneo", idtorneo).execute()
    if not t_res.data:
        return {"idalumno": idalumno, "ok": False, "error": "Torneo no encontrado"}
    torneo = t_res.data[0]

    # Verificar max participantes
    if torneo.get("max_participantes"):
        count = db.table("inscripciones_torneo").select("idinscripcion")\
            .eq("idtorneo", idtorneo).neq("estatus_pago", "cancelado").execute()
        if len(count.data) >= torneo["max_participantes"]:
            return {"idalumno": idalumno, "ok": False, "error": "Torneo lleno"}

    peso_final = peso_actual or al.get("peso")

    # Crear inscripción
    insc = {
        "idtorneo":   idtorneo,
        "idalumno":   idalumno,
        "idescuela":  al["idescuela"],
        "peso_declarado": peso_final,
        "estatus_pago": EstatusInscripcion.PENDIENTE_PAGO.value,
        "token_qr":   None,
        "qr_usado":   False,
        "inscrito_por": user.get("idusuario"),
    }
    insc_res = db.table("inscripciones_torneo").insert(insc).execute()
    idinscripcion = insc_res.data[0]["idinscripcion"] if insc_res.data else None

    # Generar pago pendiente
    nombre_al = f"{al['nombres']} {al['apellidopaterno']}"
    pago = {
        "idalumno":     idalumno,
        "idescuela":    al["idescuela"],
        "id_tipo_pago": 4,   # TORNEO
        "monto":        (torneo.get("monto_inscripcion") or torneo.get("costo_inscripcion", 0)),
        "concepto":     f"Inscripción torneo: {torneo['nombre']}",
        "folio_recibo": _folio_torneo(),
        "estatus":      0,   # PENDIENTE
        "fecha_pago":   torneo["fecha"],
        "desglose_interno": {
            "tipo":           "torneo",
            "idtorneo":       idtorneo,
            "idinscripcion":  idinscripcion,
            "nombre_torneo":  torneo["nombre"],
        },
    }
    pago_res = db.table("pagos").insert(pago).execute()
    idpago = pago_res.data[0]["idpago"] if pago_res.data else None

    # Vincular pago a inscripción
    if idinscripcion and idpago:
        db.table("inscripciones_torneo").update({"idpago": idpago})\
            .eq("idinscripcion", idinscripcion).execute()

    # Notificar al tutor por correo
    correo = al.get("correotutor")
    if correo:
        from utils.notificaciones import send_email
        escuela_res = db.table("datosescuela").select("nombreescuela")\
            .eq("idescuela", al["idescuela"]).execute()
        nombre_esc = escuela_res.data[0]["nombreescuela"] if escuela_res.data else "Tu Academia"

        html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:0}}
  .w{{max-width:520px;margin:32px auto;background:#fff;border-radius:20px;
      box-shadow:0 4px 24px rgba(0,0,0,.10);overflow:hidden}}
  .h{{background:linear-gradient(135deg,#7c3aed,#f59e0b);padding:28px;text-align:center}}
  .h h1{{color:#fff;margin:0;font-size:20px;font-weight:900}}
  .h p{{color:rgba(255,255,255,.8);margin:6px 0 0;font-size:12px}}
  .b{{padding:24px}}
  .row{{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #f1f5f9}}
  .row span:first-child{{color:#64748b;font-size:13px}}
  .row span:last-child{{color:#0f172a;font-size:13px;font-weight:700}}
  .monto{{font-size:28px;font-weight:900;color:#7c3aed;text-align:center;padding:16px 0}}
  .note{{background:#fef3c7;border:1px solid #fde68a;border-radius:10px;
         padding:12px;font-size:13px;color:#92400e;margin-top:12px}}
  .foot{{background:#f8fafc;padding:14px;text-align:center;color:#94a3b8;
         font-size:11px;border-top:1px solid #e2e8f0}}
</style></head><body>
<div class="w">
  <div class="h"><h1>🏆 {nombre_esc}</h1><p>Inscripción a torneo</p></div>
  <div class="b">
    <p style="font-size:14px;color:#374151;margin-bottom:16px">
      El alumno <strong>{nombre_al}</strong> ha sido inscrito en el siguiente torneo:
    </p>
    <div class="row"><span>Torneo</span><span>{torneo['nombre']}</span></div>
    <div class="row"><span>Fecha</span><span>{torneo['fecha']}</span></div>
    <div class="row"><span>Sede</span><span>{torneo['sede']}, {torneo['ciudad']}</span></div>
    <div class="monto">${torneo['monto_inscripcion']:,.0f} MXN</div>
    <div class="note">
      ⚠️ Para confirmar la inscripción debes realizar el pago antes del evento.
      Una vez confirmado recibirás el QR de acceso.
    </div>
  </div>
  <div class="foot">Generado automáticamente · TKW System</div>
</div></body></html>"""

        send_email(
            correo,
            f"Inscripción a torneo — {torneo['nombre']} | {nombre_esc}",
            html, nombre_esc,
        )

    return {"idalumno": idalumno, "ok": True, "idinscripcion": idinscripcion, "idpago": idpago}


@router.post("/{idtorneo}/inscribir", summary="Inscribir un alumno al torneo")
async def inscribir_alumno(
    idtorneo: int,
    body: InscribirAlumno,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["Escuela", "Profesor"])
    idescuela = _get_idescuela(user, db)
    result = await _inscribir_uno(idtorneo, body.idalumno, body.peso_actual, idescuela, user, db)
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    return {"ok": True, **result}


@router.post("/{idtorneo}/inscribir/lote", summary="Inscribir múltiples alumnos al torneo")
async def inscribir_lote(
    idtorneo: int,
    body: InscribirAlumnosLote,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["Escuela", "Profesor"])
    idescuela = _get_idescuela(user, db)

    resultados = []
    for idalumno in body.idalumnos:
        r = await _inscribir_uno(idtorneo, idalumno, body.peso_actual, idescuela, user, db)
        resultados.append(r)

    ok    = [r for r in resultados if r["ok"]]
    errores = [r for r in resultados if not r["ok"]]
    return {"ok": True, "inscritos": len(ok), "errores": errores, "resultados": resultados}


@router.post("/{idtorneo}/inscribir/con-peso", summary="Inscribir alumnos con peso individual")
async def inscribir_con_peso(
    idtorneo: int,
    body: InscribirAlumnosConPeso,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["Escuela", "Profesor"])
    idescuela = _get_idescuela(user, db)

    resultados = []
    for item in body.alumnos:
        idalumno = item.get("idalumno")
        peso     = item.get("peso_actual")
        r = await _inscribir_uno(idtorneo, idalumno, peso, idescuela, user, db)
        resultados.append(r)

    ok      = [r for r in resultados if r["ok"]]
    errores = [r for r in resultados if not r["ok"]]
    return {"ok": True, "inscritos": len(ok), "errores": errores, "resultados": resultados}


# ─────────────────────────────────────────────────────────────
#  4. GENERAR Y ENVIAR QR
# ─────────────────────────────────────────────────────────────

@router.post("/{idtorneo}/generar-qr/{idalumno}", summary="Generar QR cuando el pago está confirmado")
async def generar_qr(
    idtorneo: int,
    idalumno: int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["Escuela", "Profesor", "SuperAdmin"])

    # Buscar inscripción
    insc_res = db.table("inscripciones_torneo").select("*")\
        .eq("idtorneo", idtorneo).eq("idalumno", idalumno)\
        .neq("estatus_pago", "cancelado").execute()
    if not insc_res.data:
        raise HTTPException(404, "Inscripción no encontrada")
    insc = insc_res.data[0]

    # Verificar que el pago esté confirmado
    if insc.get("estatus_pago") != EstatusInscripcion.PAGADO.value:
        raise HTTPException(400, "El pago aún no está confirmado. Confirma el pago primero.")

    # Si ya tiene QR, solo reenviar
    token = insc.get("token_qr")
    if not token:
        token = generar_token_qr()
        db.table("inscripciones_torneo").update({"token_qr": token})\
            .eq("idinscripcion", insc["idinscripcion"]).execute()

    # Datos del alumno y torneo
    al_res = db.table("alumnos").select(
        "nombres, apellidopaterno, fechanacimiento, correotutor, "
        "cintasgrados(idgrado, nivelkupdan, color)"
    ).eq("idalumno", idalumno).execute()
    al = al_res.data[0]

    t_res  = db.table("torneos").select("*").eq("idtorneo", idtorneo).execute()
    torneo = t_res.data[0]

    nombre_alumno = f"{al['nombres']} {al['apellidopaterno']}"
    cinta         = (al.get("cintasgrados") or {}).get("nivelkupdan", "Sin cinta")
    edad          = _calcular_edad(al.get("fechanacimiento", ""))

    # Generar PDF
    pdf_bytes = generar_pdf_qr(
        token          = token,
        nombre_alumno  = nombre_alumno,
        nombre_torneo  = torneo["nombre"],
        fecha_torneo   = torneo["fecha"],
        hora_torneo    = torneo.get("hora_inicio", "09:00"),
        sede_torneo    = torneo["sede"],
        ciudad_torneo  = torneo["ciudad"],
        cinta          = cinta,
        edad           = edad,
        peso           = insc.get("peso_declarado"),
    )

    # Enviar por correo si tiene
    correo    = al.get("correotutor")
    email_ok  = False
    if correo:
        email_ok = enviar_qr_por_correo(
            correo_tutor  = correo,
            nombre_alumno = nombre_alumno,
            nombre_torneo = torneo["nombre"],
            fecha_torneo  = torneo["fecha"],
            hora_torneo   = torneo.get("hora_inicio", "09:00"),
            sede_torneo   = torneo["sede"],
            ciudad_torneo = torneo["ciudad"],
            pdf_bytes     = pdf_bytes,
        )

    return {
        "ok":         True,
        "token":      token,
        "email_ok":   email_ok,
        "mensaje":    "QR generado y enviado por correo" if email_ok else "QR generado (sin correo registrado)",
    }


@router.get("/{idtorneo}/descargar-qr/{idalumno}", summary="Descargar QR en PDF")
async def descargar_qr(
    idtorneo: int,
    idalumno: int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["Escuela", "Profesor", "SuperAdmin"])

    insc_res = db.table("inscripciones_torneo").select("*")\
        .eq("idtorneo", idtorneo).eq("idalumno", idalumno)\
        .neq("estatus_pago", "cancelado").execute()
    if not insc_res.data:
        raise HTTPException(404, "Inscripción no encontrada")
    insc = insc_res.data[0]

    if insc.get("estatus_pago") != EstatusInscripcion.PAGADO.value:
        raise HTTPException(400, "Pago no confirmado")

    token = insc.get("token_qr")
    if not token:
        raise HTTPException(400, "QR no generado aún. Usa el endpoint generar-qr primero.")

    al_res = db.table("alumnos").select(
        "nombres, apellidopaterno, fechanacimiento, cintasgrados(nombre_cinta)"
    ).eq("idalumno", idalumno).execute()
    al     = al_res.data[0]
    t_res  = db.table("torneos").select("*").eq("idtorneo", idtorneo).execute()
    torneo = t_res.data[0]

    nombre_alumno = f"{al['nombres']} {al['apellidopaterno']}"
    cinta         = (al.get("cintasgrados") or {}).get("nivelkupdan", "Sin cinta")
    edad          = _calcular_edad(al.get("fechanacimiento", ""))

    pdf_bytes = generar_pdf_qr(
        token, nombre_alumno, torneo["nombre"],
        torneo["fecha"], torneo.get("hora_inicio", "09:00"),
        torneo["sede"], torneo["ciudad"], cinta, edad,
        insc.get("peso_declarado"),
    )

    filename = f"QR_{nombre_alumno.replace(' ', '_')}_{torneo['nombre'].replace(' ', '_')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─────────────────────────────────────────────────────────────
#  5. VALIDAR QR (día del torneo)
# ─────────────────────────────────────────────────────────────

@router.post("/validar-qr", summary="Escanear QR el día del torneo")
async def validar_qr(
    body: ValidarQR,
    db:   Client = Depends(get_db),
):
    """Endpoint público — cualquier dispositivo puede escanear."""
    insc_res = db.table("inscripciones_torneo").select(
        "*, alumnos(nombres, apellidopaterno), torneos(nombre, fecha)"
    ).eq("token_qr", body.token).execute()

    if not insc_res.data:
        raise HTTPException(404, "QR inválido o no encontrado")

    insc   = insc_res.data[0]
    al     = insc.get("alumnos") or {}
    torneo = insc.get("torneos") or {}

    nombre_alumno = f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip()

    # Ya fue usado
    if insc.get("qr_usado"):
        return {
            "ok":           False,
            "idalumno":     insc["idalumno"],
            "nombre_alumno": nombre_alumno,
            "torneo":       torneo.get("nombre", ""),
            "mensaje":      "⚠️ Este QR ya fue utilizado anteriormente.",
        }

    # Pago no confirmado
    if insc.get("estatus_pago") != EstatusInscripcion.PAGADO.value:
        return {
            "ok":           False,
            "idalumno":     insc["idalumno"],
            "nombre_alumno": nombre_alumno,
            "torneo":       torneo.get("nombre", ""),
            "mensaje":      "❌ El pago de este participante no está confirmado.",
        }

    # Marcar QR como usado y registrar asistencia
    db.table("inscripciones_torneo").update({
        "qr_usado":       True,
        "hora_llegada":   datetime.now().isoformat(),
        "estatus_checkin": True,
    }).eq("idinscripcion", insc["idinscripcion"]).execute()

    return {
        "ok":           True,
        "idalumno":     insc["idalumno"],
        "nombre_alumno": nombre_alumno,
        "torneo":       torneo.get("nombre", ""),
        "mensaje":      f"✅ Bienvenido {nombre_alumno}. Acceso confirmado.",
    }


# ─────────────────────────────────────────────────────────────
#  6. ASISTENCIA
# ─────────────────────────────────────────────────────────────

@router.get("/{idtorneo}/asistencia", summary="Lista de asistentes al torneo")
async def asistencia_torneo(
    idtorneo: int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["Escuela", "Profesor", "SuperAdmin"])

    r = db.table("inscripciones_torneo").select(
        "idinscripcion, idalumno, peso_inscripcion, hora_llegada, asistio, estatus, "
        "alumnos(nombres, apellidopaterno, fechanacimiento, genero, cintasgrados(nombre_cinta, color)), "
        "datosescuela(nombreescuela)"
    ).eq("idtorneo", idtorneo).execute()

    asistentes    = []
    no_asistentes = []

    for insc in r.data:
        al    = insc.get("alumnos") or {}
        cinta = (al.get("cintasgrados") or {})
        esc   = insc.get("datosescuela") or {}
        item  = {
            "idalumno":        insc["idalumno"],
            "nombre":          f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip(),
            "edad":            _calcular_edad(al.get("fechanacimiento", "")),
            "cinta":           cinta.get("nivelkupdan", ""),
            "color_cinta":     cinta.get("color", ""),
            "peso":            insc.get("peso_declarado"),
            "genero":          al.get("genero"),
            "escuela":         esc.get("nombreescuela", ""),
            "hora_llegada":    insc.get("hora_llegada"),
            "estatus_pago":    insc.get("estatus"),
        }
        if insc.get("estatus_checkin"):
            asistentes.append(item)
        else:
            no_asistentes.append(item)

    return {
        "ok":             True,
        "total_inscritos": len(r.data),
        "asistentes":     len(asistentes),
        "no_asistentes":  len(no_asistentes),
        "lista_asistentes":     asistentes,
        "lista_no_asistentes":  no_asistentes,
    }


# ─────────────────────────────────────────────────────────────
#  7. MATCHMAKING
# ─────────────────────────────────────────────────────────────

@router.get("/{idtorneo}/matchmaking", summary="Generar enfrentamientos por categoría")
async def matchmaking(
    idtorneo:        int,
    solo_asistentes: bool = Query(True, description="True=solo los que llegaron, False=todos los inscritos pagados"),
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["Escuela", "Profesor", "SuperAdmin"])

    q = db.table("inscripciones_torneo").select(
        "idalumno, peso_inscripcion, "
        "alumnos(idalumno, nombres, apellidopaterno, fechanacimiento, genero, idescuela, "
        "cintasgrados(nombre_cinta, color)), "
        "datosescuela(nombreescuela)"
    ).eq("idtorneo", idtorneo).eq("estatus_pago", EstatusInscripcion.PAGADO.value)

    if solo_asistentes:
        q = q.eq("estatus_checkin", True)

    r = q.execute()

    if not r.data:
        raise HTTPException(404, "No hay participantes para generar el matchmaking")

    participantes = []
    for insc in r.data:
        al    = insc.get("alumnos") or {}
        cinta = (al.get("cintasgrados") or {})
        esc   = insc.get("datosescuela") or {}
        participantes.append({
            "idalumno":        al.get("idalumno") or insc["idalumno"],
            "nombres":         al.get("nombres", ""),
            "apellidopaterno": al.get("apellidopaterno", ""),
            "edad":            _calcular_edad(al.get("fechanacimiento", "")),
            "cinta":           cinta.get("nivelkupdan", "Sin cinta"),
            "color_cinta":     cinta.get("color", "#888"),
            "peso":            insc.get("peso_declarado") or al.get("peso"),
            "genero":          al.get("genero"),
            "idescuela":       al.get("idescuela"),
            "nombreescuela":   esc.get("nombreescuela", ""),
        })

    categorias = generar_matchmaking(participantes)
    resumen    = resumen_matchmaking(categorias)

    return {
        "ok":         True,
        "idtorneo":   idtorneo,
        "resumen":    resumen,
        "categorias": categorias,
    }


# ─────────────────────────────────────────────────────────────
#  8. INSCRIPCIONES DEL TORNEO (lista completa)
# ─────────────────────────────────────────────────────────────

@router.get("/{idtorneo}/inscripciones", summary="Lista de inscritos con estatus de pago")
async def inscripciones_torneo(
    idtorneo: int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["Escuela", "Profesor", "SuperAdmin"])

    idescuela = _get_idescuela(user, db)

    q = db.table("inscripciones_torneo").select(
        "idinscripcion, idalumno, peso_inscripcion, estatus, qr_token, qr_usado, "
        "fecharegistro, asistio, hora_llegada, "
        "alumnos(nombres, apellidopaterno, fechanacimiento, genero, cintasgrados(nombre_cinta, color)), "
        "datosescuela(nombreescuela)"
    ).eq("idtorneo", idtorneo)

    # Escuela y Profesor solo ven los de su escuela
    if idescuela:
        q = q.eq("idescuela", idescuela)

    r = q.execute()

    inscritos = []
    for insc in r.data:
        al    = insc.get("alumnos") or {}
        cinta = (al.get("cintasgrados") or {})
        esc   = insc.get("datosescuela") or {}
        inscritos.append({
            "idinscripcion":   insc["idinscripcion"],
            "idalumno":        insc["idalumno"],
            "nombre_alumno":   f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip(),
            "edad":            _calcular_edad(al.get("fechanacimiento", "")),
            "cinta":           cinta.get("nivelkupdan", ""),
            "color_cinta":     cinta.get("color", ""),
            "peso":            insc.get("peso_declarado"),
            "genero":          al.get("genero"),
            "escuela":         esc.get("nombreescuela", ""),
            "estatus_pago":    insc["estatus"],
            "qr_generado":     insc.get("token_qr") is not None,
            "qr_usado":        insc.get("qr_usado", False),
            "asistio":         insc.get("asistio", False),
            "hora_llegada":    insc.get("hora_llegada"),
            "fecha_inscripcion": str(insc.get("fecharegistro", ""))[:10],
        })

    return {"ok": True, "total": len(inscritos), "inscritos": inscritos}