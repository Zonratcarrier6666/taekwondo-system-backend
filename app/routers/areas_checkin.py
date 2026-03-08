# ============================================================
#  app/routers/areas_checkin.py
#
#  Cubre los flujos NUEVOS del sistema de torneos v2:
#
#  ÁREAS DE COMBATE
#    POST /torneos/{id}/areas              → crear área (SuperAdmin)
#    GET  /torneos/{id}/areas              → listar áreas del torneo
#    PUT  /torneos/{id}/areas/{idarea}     → editar área / reasignar juez
#    DELETE /torneos/{id}/areas/{idarea}   → eliminar área
#
#  CHECK-IN (día del torneo)
#    GET  /torneos/{id}/checkin/pendientes → inscritos pagados sin check-in
#    POST /torneos/{id}/checkin/{idinsc}   → staff confirma llegada y genera QR
#    POST /torneos/{id}/checkin/lote       → confirmar varios a la vez
#
#  ESCANEO QR (juez en el área)
#    POST /qr/escanear                     → juez escanea QR, verifica área, retorna pantalla
#    POST /qr/invalidar/{idinsc}           → invalida QR al perder (competencia)
#
#  MODALIDAD LOCAL
#    POST /combates/{id}/resultado-local   → juez declara ganador (sin puntos) + asigna lugar
#    POST /torneos/{id}/podio              → asignar 1°/2°/3° manualmente
#    GET  /torneos/{id}/resultados-local   → tabla de posiciones
#
#  MATCHMAKING EDITABLE
#    GET  /torneos/{id}/matchmaking/preview  → vista previa de emparejamientos
#    PUT  /torneos/{id}/matchmaking/reasignar → mover competidor a otro combate
#    POST /torneos/{id}/matchmaking/confirmar → confirmar y guardar combates en BD
#
# ============================================================

import math
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from supabase import Client

from utils.database   import get_db
from utils.auth_utils import get_current_user

router = APIRouter(tags=["Torneos y Competencias"])


# ─── Helpers ─────────────────────────────────────────────────

def _require_roles(user: dict, roles: list):
    if user.get("rol") not in roles:
        raise HTTPException(403, "Sin acceso para esta operación")

def _calcular_edad(fecha_nac: str) -> int:
    from datetime import date
    try:
        fn  = date.fromisoformat(str(fecha_nac)[:10])
        hoy = date.today()
        return hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
    except:
        return 0

def _siguiente_potencia_2(n: int) -> int:
    if n <= 1: return 1
    return 2 ** math.ceil(math.log2(n))


# ─── Schemas ─────────────────────────────────────────────────

class CrearArea(BaseModel):
    nombre_area:      str              # "Área 1", "Ring A", etc.
    idjuez_asignado:  Optional[int] = None

class EditarArea(BaseModel):
    nombre_area:      Optional[str] = None
    idjuez_asignado:  Optional[int] = None
    estatus:          Optional[str] = None   # disponible | en_combate | inactiva

class CheckinLote(BaseModel):
    idinscripciones: list[int]

class ResultadoLocal(BaseModel):
    id_ganador:    int   # idinscripcion del ganador
    # No se pasan puntos — el juez solo dice quién ganó

class AsignarPodio(BaseModel):
    # Lista de { idinscripcion, lugar } para asignar manualmente
    podio: list[dict]   # [{"idinscripcion": 5, "lugar": 1}, ...]

class ReasignarMatchmaking(BaseModel):
    # Intercambiar dos competidores entre combates o mover uno
    idinscripcion_a: int
    idinscripcion_b: int   # con quién se intercambia (puede ser None para BYE)


# ═════════════════════════════════════════════════════════════
#  ÁREAS DE COMBATE
# ═════════════════════════════════════════════════════════════

@router.post("/torneos/{idtorneo}/areas",
             summary="Crear área/ring de combate en el torneo")
async def crear_area(
    idtorneo: int,
    body: CrearArea,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["SuperAdmin"])

    # Verificar torneo
    t = db.table("torneos").select("idtorneo, nombre").eq("idtorneo", idtorneo).execute()
    if not t.data:
        raise HTTPException(404, "Torneo no encontrado")

    # Verificar juez si se asigna
    if body.idjuez_asignado:
        u = db.table("usuarios").select("idusuario, username, rol")\
            .eq("idusuario", body.idjuez_asignado).execute()
        if not u.data:
            raise HTTPException(404, "Usuario juez no encontrado")
        if u.data[0].get("rol") not in ["Juez", "SuperAdmin"]:
            raise HTTPException(400, "El usuario asignado debe tener rol Juez")

    area = db.table("areas_combate").insert({
        "idtorneo":        idtorneo,
        "nombre_area":     body.nombre_area,
        "idjuez_asignado": body.idjuez_asignado,
        "estatus":         "disponible",
    }).execute()

    return {"ok": True, "area": area.data[0] if area.data else {}}


@router.get("/torneos/{idtorneo}/areas",
            summary="Listar áreas/rings del torneo con su juez asignado")
async def listar_areas(
    idtorneo: int,
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    areas_res = db.table("areas_combate").select(
        "idarea, nombre_area, estatus, idjuez_asignado, idcategoria_actual, "
        "usuarios!areas_combate_idjuez_asignado_fkey(idusuario, username)"
    ).eq("idtorneo", idtorneo).order("idarea").execute()

    areas = []
    for a in areas_res.data or []:
        juez = a.get("usuarios") or {}
        # Combates pendientes de esta área
        pendientes = db.table("combates").select("idcombate")\
            .eq("idarea", a["idarea"])\
            .eq("estatus", "pendiente").execute()
        areas.append({
            "idarea":           a["idarea"],
            "nombre_area":      a["nombre_area"],
            "estatus":          a["estatus"],
            "idjuez_asignado":  a["idjuez_asignado"],
            "juez_username":    juez.get("username"),
            "combates_pendientes": len(pendientes.data or []),
        })

    return {"ok": True, "areas": areas, "total": len(areas)}


@router.put("/torneos/{idtorneo}/areas/{idarea}",
            summary="Editar área: renombrar, reasignar juez o cambiar estatus")
async def editar_area(
    idtorneo: int,
    idarea:   int,
    body:     EditarArea,
    user:     dict = Depends(get_current_user),
    db:       Client = Depends(get_db),
):
    _require_roles(user, ["SuperAdmin", "Staff"])

    a = db.table("areas_combate").select("*")\
        .eq("idarea", idarea).eq("idtorneo", idtorneo).execute()
    if not a.data:
        raise HTTPException(404, "Área no encontrada")

    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if not upd:
        raise HTTPException(400, "Nada que actualizar")

    # Validar juez si se cambia
    if "idjuez_asignado" in upd:
        u = db.table("usuarios").select("rol")\
            .eq("idusuario", upd["idjuez_asignado"]).execute()
        if not u.data or u.data[0].get("rol") not in ["Juez", "SuperAdmin"]:
            raise HTTPException(400, "El usuario debe tener rol Juez")

    db.table("areas_combate").update(upd).eq("idarea", idarea).execute()
    return {"ok": True, "mensaje": "Área actualizada"}


@router.delete("/torneos/{idtorneo}/areas/{idarea}",
               summary="Eliminar área (solo si no tiene combates asignados)")
async def eliminar_area(
    idtorneo: int,
    idarea:   int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["SuperAdmin"])

    combates = db.table("combates").select("idcombate")\
        .eq("idarea", idarea).execute()
    if combates.data:
        raise HTTPException(400,
            f"No se puede eliminar — el área tiene {len(combates.data)} combate(s) asignado(s)")

    db.table("areas_combate").delete().eq("idarea", idarea).execute()
    return {"ok": True, "mensaje": "Área eliminada"}


# ═════════════════════════════════════════════════════════════
#  CHECK-IN (día del torneo)
# ═════════════════════════════════════════════════════════════

@router.get("/torneos/{idtorneo}/checkin/pendientes",
            summary="Lista de inscritos pagados pendientes de check-in")
async def checkin_pendientes(
    idtorneo: int,
    idescuela: Optional[int] = Query(None, description="Filtrar por escuela"),
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_roles(user, ["SuperAdmin", "Staff", "Escuela", "Profesor"])

    q = db.table("inscripciones_torneo").select(
        "idinscripcion, idalumno, idescuela, idcategoria, "
        "peso_declarado, estatus_pago, estatus_checkin, token_qr, "
        "alumnos(nombres, apellidopaterno, apellidomaterno, fotoalumno, "
        "  fechanacimiento, cintasgrados(nivelkupdan, color)), "
        "datosescuela!inscripciones_torneo_idescuela_fkey(nombreescuela), "
        "torneo_categorias(nombre_categoria)"
    ).eq("idtorneo", idtorneo).eq("estatus_pago", "Pagado")

    if idescuela:
        q = q.eq("idescuela", idescuela)

    res = q.execute()
    inscritos = res.data or []

    pendientes  = []
    con_checkin = []

    for i in inscritos:
        al  = i.get("alumnos") or {}
        cg  = al.get("cintasgrados") or {}
        esc = i.get("datosescuela") or {}
        cat = i.get("torneo_categorias") or {}

        item = {
            "idinscripcion":   i["idinscripcion"],
            "idalumno":        i["idalumno"],
            "nombre_alumno":   f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip(),
            "foto":            al.get("fotoalumno"),
            "edad":            _calcular_edad(al.get("fechanacimiento", "")),
            "cinta":           cg.get("nivelkupdan", ""),
            "color_cinta":     cg.get("color", ""),
            "peso_declarado":  i.get("peso_declarado"),
            "escuela":         esc.get("nombreescuela", ""),
            "idescuela":       i.get("idescuela"),
            "categoria":       cat.get("nombre_categoria", "Sin categoría"),
            "estatus_checkin": i.get("estatus_checkin", False),
            "tiene_qr":        bool(i.get("token_qr")),
        }

        if i.get("estatus_checkin"):
            con_checkin.append(item)
        else:
            pendientes.append(item)

    return {
        "ok":            True,
        "total_pagados": len(inscritos),
        "pendientes":    pendientes,
        "con_checkin":   con_checkin,
    }


@router.post("/torneos/{idtorneo}/checkin/{idinscripcion}",
             summary="Staff confirma llegada y genera QR/gafete del competidor")
async def hacer_checkin(
    idtorneo:      int,
    idinscripcion: int,
    peso_bascula:  Optional[float] = Body(None, description="Peso real en báscula el día del torneo"),
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_roles(user, ["SuperAdmin", "Staff", "Escuela"])

    # Verificar inscripción
    insc_res = db.table("inscripciones_torneo").select(
        "*, alumnos(nombres, apellidopaterno, fotoalumno, fechanacimiento), "
        "torneo_categorias(nombre_categoria), "
        "datosescuela!inscripciones_torneo_idescuela_fkey(nombreescuela), "
        "torneos(nombre, fecha, sede)"
    ).eq("idinscripcion", idinscripcion).eq("idtorneo", idtorneo).execute()

    if not insc_res.data:
        raise HTTPException(404, "Inscripción no encontrada en este torneo")

    insc = insc_res.data[0]

    if insc.get("estatus_pago") != "Pagado":
        raise HTTPException(400,
            f"El competidor no tiene pago confirmado (estatus: {insc.get('estatus_pago')}). "
            "Confirma el pago en Caja antes del check-in.")

    if insc.get("estatus_checkin"):
        # Ya hizo check-in — devolver el QR existente
        return {
            "ok":      True,
            "mensaje": "Este competidor ya hizo check-in anteriormente",
            "ya_existia": True,
            "token_qr": insc.get("token_qr"),
            "datos_gafete": _armar_gafete(insc),
        }

    # Generar QR único
    token = str(uuid.uuid4())

    upd = {
        "estatus_checkin": True,
        "token_qr":        token,
        "hora_llegada":    datetime.now().isoformat(),
        "asistio":         True,
        "qr_usado":        False,   # False = QR activo (aún no perdió)
    }
    if peso_bascula is not None:
        upd["peso_bascula"] = peso_bascula

    db.table("inscripciones_torneo").update(upd)\
        .eq("idinscripcion", idinscripcion).execute()

    return {
        "ok":           True,
        "mensaje":      "Check-in realizado. QR generado para el gafete.",
        "ya_existia":   False,
        "token_qr":     token,
        "datos_gafete": _armar_gafete(insc, token_override=token),
    }


@router.post("/torneos/{idtorneo}/checkin/lote",
             summary="Check-in en lote (varios competidores de la misma escuela)")
async def checkin_lote(
    idtorneo: int,
    body: CheckinLote,
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_roles(user, ["SuperAdmin", "Staff", "Escuela"])

    resultados = []
    for idinsc in body.idinscripciones:
        try:
            # Reutilizar la lógica del check-in individual
            insc_res = db.table("inscripciones_torneo").select("*")\
                .eq("idinscripcion", idinsc).eq("idtorneo", idtorneo).execute()
            if not insc_res.data:
                resultados.append({"idinscripcion": idinsc, "ok": False, "error": "No encontrado"})
                continue

            insc = insc_res.data[0]
            if insc.get("estatus_pago") != "Pagado":
                resultados.append({"idinscripcion": idinsc, "ok": False, "error": "Sin pago confirmado"})
                continue

            if insc.get("estatus_checkin"):
                resultados.append({
                    "idinscripcion": idinsc, "ok": True,
                    "token_qr": insc.get("token_qr"), "ya_existia": True
                })
                continue

            token = str(uuid.uuid4())
            db.table("inscripciones_torneo").update({
                "estatus_checkin": True,
                "token_qr":        token,
                "hora_llegada":    datetime.now().isoformat(),
                "asistio":         True,
                "qr_usado":        False,
            }).eq("idinscripcion", idinsc).execute()

            resultados.append({"idinscripcion": idinsc, "ok": True, "token_qr": token, "ya_existia": False})

        except Exception as e:
            resultados.append({"idinscripcion": idinsc, "ok": False, "error": str(e)})

    exitosos = [r for r in resultados if r["ok"]]
    return {
        "ok":        True,
        "total":     len(body.idinscripciones),
        "exitosos":  len(exitosos),
        "fallidos":  len(resultados) - len(exitosos),
        "detalle":   resultados,
    }


def _armar_gafete(insc: dict, token_override: str = None) -> dict:
    """Datos completos para imprimir el gafete con QR."""
    al  = insc.get("alumnos") or {}
    cat = insc.get("torneo_categorias") or {}
    esc = insc.get("datosescuela") or {}
    tor = insc.get("torneos") or {}

    return {
        "nombre_alumno":   f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip(),
        "foto":            al.get("fotoalumno"),
        "edad":            _calcular_edad(al.get("fechanacimiento", "")),
        "escuela":         esc.get("nombreescuela", ""),
        "categoria":       cat.get("nombre_categoria", ""),
        "torneo":          tor.get("nombre", ""),
        "fecha_torneo":    str(tor.get("fecha", "")),
        "sede":            tor.get("sede", ""),
        "token_qr":        token_override or insc.get("token_qr", ""),
        "idinscripcion":   insc.get("idinscripcion"),
    }


# ═════════════════════════════════════════════════════════════
#  ESCANEO QR (juez en el área)
# ═════════════════════════════════════════════════════════════

@router.post("/qr/escanear",
             summary="Juez escanea QR del gafete — verifica área y retorna pantalla Juan vs Pepe")
async def escanear_qr(
    token:   str = Body(..., embed=True),
    idarea:  Optional[int] = Body(None, embed=True),
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_roles(user, ["Juez", "SuperAdmin", "Staff"])

    # Buscar inscripción por token
    insc_res = db.table("inscripciones_torneo").select(
        "idinscripcion, idtorneo, idcategoria, idescuela, idarea_asignada, "
        "estatus_checkin, qr_usado, num_combates_realizados, lugar_obtenido, "
        "alumnos(nombres, apellidopaterno, fotoalumno, fechanacimiento, "
        "  cintasgrados(nivelkupdan, color)), "
        "datosescuela!inscripciones_torneo_idescuela_fkey(nombreescuela), "
        "torneos(nombre, tipo_torneo, max_combates_por_competidor)"
    ).eq("token_qr", token).execute()

    if not insc_res.data:
        return {
            "ok":      False,
            "valido":  False,
            "mensaje": "QR inválido o no encontrado",
        }

    insc = insc_res.data[0]
    al   = insc.get("alumnos") or {}
    cg   = al.get("cintasgrados") or {}
    esc  = insc.get("datosescuela") or {}
    tor  = insc.get("torneos") or {}

    nombre = f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip()

    # ── Validaciones ──
    if not insc.get("estatus_checkin"):
        return {
            "ok": False, "valido": False,
            "nombre_alumno": nombre,
            "mensaje": "⚠️ Este competidor no ha hecho check-in",
        }

    if insc.get("qr_usado"):
        # En modalidad local puede tener lugar asignado
        lugar = insc.get("lugar_obtenido")
        msg   = f"🚫 QR inválido — competidor eliminado"
        if lugar:
            msg = f"🏅 Competidor finalizó en {lugar}° lugar"
        return {
            "ok": False, "valido": False,
            "nombre_alumno": nombre,
            "mensaje": msg,
            "lugar_obtenido": lugar,
        }

    tipo_torneo = tor.get("tipo_torneo", "competencia")
    max_combates = tor.get("max_combates_por_competidor", 3)
    num_realizados = insc.get("num_combates_realizados", 0)

    # Modalidad local: verificar límite de combates
    if tipo_torneo == "local" and num_realizados >= max_combates:
        return {
            "ok": False, "valido": False,
            "nombre_alumno": nombre,
            "mensaje": f"⚠️ Competidor alcanzó el límite de {max_combates} combates en modalidad local",
            "num_combates_realizados": num_realizados,
        }

    # Verificar área correcta
    area_asignada = insc.get("idarea_asignada")
    en_area_correcta = True
    nombre_area_correcta = None
    nombre_area_actual   = None

    if idarea and area_asignada and idarea != area_asignada:
        en_area_correcta = False
        # Obtener nombres de las áreas
        area_correcta_res = db.table("areas_combate").select("nombre_area")\
            .eq("idarea", area_asignada).execute()
        area_actual_res   = db.table("areas_combate").select("nombre_area")\
            .eq("idarea", idarea).execute()
        nombre_area_correcta = area_correcta_res.data[0]["nombre_area"] if area_correcta_res.data else f"Área {area_asignada}"
        nombre_area_actual   = area_actual_res.data[0]["nombre_area"]   if area_actual_res.data   else f"Área {idarea}"

    # Buscar combate activo del competidor
    combate_activo = None
    if idarea:
        idinscripcion = insc["idinscripcion"]
        idtorneo_insc = insc["idtorneo"]

        # Primero buscar combate asignado específicamente a esta área
        c_res = db.table("combates").select(
            "idcombate, id_competidor_1, id_competidor_2, ronda, estatus, idarea"
        ).eq("idtorneo", idtorneo_insc).eq("estatus", "pendiente")\
         .eq("idarea", idarea).execute()

        for c in c_res.data or []:
            if c.get("id_competidor_1") == idinscripcion or \
               c.get("id_competidor_2") == idinscripcion:
                combate_activo = c
                break

        # Si no encontró con área, buscar cualquier combate pendiente del torneo
        if not combate_activo:
            c_res2 = db.table("combates").select(
                "idcombate, id_competidor_1, id_competidor_2, ronda, estatus, idarea"
            ).eq("idtorneo", idtorneo_insc).eq("estatus", "pendiente")\
             .is_("idarea", "null").execute()

            for c in c_res2.data or []:
                if c.get("id_competidor_1") == idinscripcion or \
                   c.get("id_competidor_2") == idinscripcion:
                    combate_activo = c
                    # Asignar el área a este combate automáticamente
                    db.table("combates").update({"idarea": idarea})\
                        .eq("idcombate", c["idcombate"]).execute()
                    combate_activo["idarea"] = idarea
                    break

    return {
        "ok":              True,
        "valido":          True,
        "en_area_correcta": en_area_correcta,
        "nombre_alumno":   nombre,
        "foto":            al.get("fotoalumno"),
        "edad":            _calcular_edad(al.get("fechanacimiento", "")),
        "cinta":           cg.get("nivelkupdan", ""),
        "color_cinta":     cg.get("color", ""),
        "escuela":         esc.get("nombreescuela", ""),
        "idinscripcion":   insc["idinscripcion"],
        "idtorneo":        insc["idtorneo"],
        "tipo_torneo":     tipo_torneo,
        "num_combates_realizados": num_realizados,
        "max_combates":    max_combates if tipo_torneo == "local" else None,
        "combate_activo":  combate_activo,
        "mensaje": (
            f"✅ {nombre} — verificado correctamente"
            if en_area_correcta
            else f"⚠️ {nombre} pertenece a {nombre_area_correcta}, no a {nombre_area_actual}"
        ),
        # Info para redirigir si está en área incorrecta
        "area_correcta":  nombre_area_correcta,
        "area_escaneada": nombre_area_actual,
    }


@router.post("/qr/invalidar/{idinscripcion}",
             summary="Invalida el QR al perder (modalidad competencia) o asigna lugar (local)")
async def invalidar_qr(
    idinscripcion: int,
    lugar:         Optional[int] = Body(None, embed=True, description="Solo para modalidad local: 1, 2 o 3"),
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_roles(user, ["Juez", "SuperAdmin"])

    insc_res = db.table("inscripciones_torneo").select(
        "idinscripcion, qr_usado, torneos(tipo_torneo)"
    ).eq("idinscripcion", idinscripcion).execute()

    if not insc_res.data:
        raise HTTPException(404, "Inscripción no encontrada")

    insc      = insc_res.data[0]
    tor       = insc.get("torneos") or {}
    tipo_torneo = tor.get("tipo_torneo", "competencia")

    upd = {"qr_usado": True}
    if tipo_torneo == "local" and lugar:
        upd["lugar_obtenido"] = lugar

    db.table("inscripciones_torneo").update(upd)\
        .eq("idinscripcion", idinscripcion).execute()

    return {
        "ok":      True,
        "mensaje": f"QR invalidado{'  — lugar asignado: ' + str(lugar) if lugar else ''}",
    }


# ═════════════════════════════════════════════════════════════
#  MODALIDAD LOCAL: resultado + podio
# ═════════════════════════════════════════════════════════════

@router.post("/combates/{idcombate}/resultado-local",
             summary="Juez declara ganador en modalidad local (sin puntos)")
async def resultado_local(
    idcombate: int,
    body: ResultadoLocal,
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_roles(user, ["Juez", "SuperAdmin"])

    c_res = db.table("combates").select("*").eq("idcombate", idcombate).execute()
    if not c_res.data:
        raise HTTPException(404, "Combate no encontrado")
    c = c_res.data[0]

    if c.get("estatus") == "finalizado":
        raise HTTPException(400, "Este combate ya fue finalizado")

    # Validar que el ganador sea uno de los dos competidores
    if body.id_ganador not in [c.get("id_competidor_1"), c.get("id_competidor_2")]:
        raise HTTPException(400, "El ganador debe ser uno de los dos competidores del combate")

    perdedor_id = (
        c["id_competidor_2"] if body.id_ganador == c["id_competidor_1"]
        else c["id_competidor_1"]
    )

    # Verificar que el torneo es modalidad local
    tor_res = db.table("torneos").select("tipo_torneo, max_combates_por_competidor")\
        .eq("idtorneo", c["idtorneo"]).execute()
    tor = tor_res.data[0] if tor_res.data else {}
    tipo_torneo = tor.get("tipo_torneo", "competencia")

    # Actualizar combate
    db.table("combates").update({
        "id_ganador":   body.id_ganador,
        "estatus":      "finalizado",
        "tiempo_fin":   datetime.now().isoformat(),
    }).eq("idcombate", idcombate).execute()

    # Incrementar contador de combates realizados para ambos
    for idinsc in [body.id_ganador, perdedor_id]:
        insc_res = db.table("inscripciones_torneo").select("num_combates_realizados")\
            .eq("idinscripcion", idinsc).execute()
        if insc_res.data:
            actual = insc_res.data[0].get("num_combates_realizados", 0) or 0
            db.table("inscripciones_torneo")\
                .update({"num_combates_realizados": actual + 1})\
                .eq("idinscripcion", idinsc).execute()

    max_combates = tor.get("max_combates_por_competidor", 3)

    # En modalidad local: si el perdedor alcanzó el límite, invalidar su QR
    perdedor_insc = db.table("inscripciones_torneo")\
        .select("num_combates_realizados")\
        .eq("idinscripcion", perdedor_id).execute()
    if perdedor_insc.data:
        num = perdedor_insc.data[0].get("num_combates_realizados", 0) or 0
        if tipo_torneo == "competencia" or num >= max_combates:
            db.table("inscripciones_torneo")\
                .update({"qr_usado": True})\
                .eq("idinscripcion", perdedor_id).execute()

    return {
        "ok":          True,
        "idcombate":   idcombate,
        "id_ganador":  body.id_ganador,
        "id_perdedor": perdedor_id,
        "mensaje":     "Resultado registrado",
    }


@router.post("/torneos/{idtorneo}/podio",
             summary="Asignar 1°/2°/3° lugar manualmente (modalidad local)")
async def asignar_podio(
    idtorneo: int,
    body: AsignarPodio,
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_roles(user, ["SuperAdmin", "Juez"])

    # Verificar que el torneo es local
    tor = db.table("torneos").select("tipo_torneo, nombre")\
        .eq("idtorneo", idtorneo).execute()
    if not tor.data:
        raise HTTPException(404, "Torneo no encontrado")

    actualizados = []
    for item in body.podio:
        idinsc = item.get("idinscripcion")
        lugar  = item.get("lugar")
        if not idinsc or not lugar:
            continue
        db.table("inscripciones_torneo")\
            .update({"lugar_obtenido": lugar, "qr_usado": True})\
            .eq("idinscripcion", idinsc)\
            .eq("idtorneo", idtorneo).execute()
        actualizados.append({"idinscripcion": idinsc, "lugar": lugar})

    return {
        "ok":          True,
        "mensaje":     f"Podio asignado para {len(actualizados)} competidor(es)",
        "actualizados": actualizados,
    }


@router.get("/torneos/{idtorneo}/resultados-local",
            summary="Tabla de posiciones del torneo local")
async def resultados_local(
    idtorneo: int,
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    res = db.table("inscripciones_torneo").select(
        "idinscripcion, lugar_obtenido, num_combates_realizados, idcategoria, "
        "alumnos(nombres, apellidopaterno, fotoalumno), "
        "datosescuela!inscripciones_torneo_idescuela_fkey(nombreescuela), "
        "torneo_categorias(nombre_categoria)"
    ).eq("idtorneo", idtorneo)\
     .not_.is_("lugar_obtenido", "null")\
     .order("lugar_obtenido").execute()

    # Agrupar por categoría
    por_categoria: dict = {}
    for r in res.data or []:
        cat  = r.get("torneo_categorias") or {}
        cid  = r.get("idcategoria", 0)
        al   = r.get("alumnos") or {}
        esc  = r.get("datosescuela") or {}
        nombre_cat = cat.get("nombre_categoria", f"Categoría {cid}")
        por_categoria.setdefault(nombre_cat, []).append({
            "idinscripcion":     r["idinscripcion"],
            "lugar":             r["lugar_obtenido"],
            "num_combates":      r.get("num_combates_realizados", 0),
            "nombre_alumno":     f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip(),
            "foto":              al.get("fotoalumno"),
            "escuela":           esc.get("nombreescuela", ""),
        })

    return {
        "ok":         True,
        "idtorneo":   idtorneo,
        "categorias": [
            {"nombre_categoria": cat, "posiciones": sorted(pos, key=lambda x: x["lugar"])}
            for cat, pos in por_categoria.items()
        ],
    }


# ═════════════════════════════════════════════════════════════
#  MATCHMAKING EDITABLE
# ═════════════════════════════════════════════════════════════

@router.get("/torneos/{idtorneo}/matchmaking/preview",
            summary="Vista previa de emparejamientos antes de confirmar")
async def matchmaking_preview(
    idtorneo:   int,
    idcategoria: Optional[int] = Query(None),
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_roles(user, ["SuperAdmin"])

    # Traer asistentes pagados con check-in
    q = db.table("inscripciones_torneo").select(
        "idinscripcion, idcategoria, peso_declarado, peso_bascula, idescuela, "
        "num_combates_realizados, "
        "alumnos(nombres, apellidopaterno, fechanacimiento, fotoalumno, "
        "  cintasgrados(nivelkupdan, color, orden)), "
        "datosescuela!inscripciones_torneo_idescuela_fkey(nombreescuela)"
    ).eq("idtorneo", idtorneo)\
     .eq("estatus_checkin", True)\
     .or_("estatus_pago.eq.Pagado,estatus_pago.eq.pagado,estatus_pago.ilike.pagado")

    if idcategoria:
        q = q.eq("idcategoria", idcategoria)

    asistentes = q.execute().data or []

    # Enriquecer con datos calculados
    enriquecidos = []
    for i in asistentes:
        al = i.get("alumnos") or {}
        cg = al.get("cintasgrados") or {}
        esc = i.get("datosescuela") or {}
        enriquecidos.append({
            "idinscripcion":   i["idinscripcion"],
            "idcategoria":     i.get("idcategoria"),
            "nombre":          f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip(),
            "foto":            al.get("fotoalumno"),
            "edad":            _calcular_edad(al.get("fechanacimiento", "")),
            "peso":            i.get("peso_bascula") or i.get("peso_declarado"),
            "cinta":           cg.get("nivelkupdan", ""),
            "color_cinta":     cg.get("color", ""),
            "orden_cinta":     cg.get("orden", 0),
            "escuela":         esc.get("nombreescuela", ""),
            "idescuela":       i.get("idescuela"),
        })

    # Generar emparejamientos sugeridos separando por escuela
    def _emparejar_preview(participantes):
        por_escuela: dict = {}
        for p in participantes:
            eid = p.get("idescuela", 0)
            por_escuela.setdefault(eid, []).append(p)

        mezclados = []
        listas = list(por_escuela.values())
        i = 0
        while any(listas):
            bucket = listas[i % len(listas)]
            if bucket:
                mezclados.append(bucket.pop(0))
            i += 1

        pares = []
        for idx in range(0, len(mezclados), 2):
            a = mezclados[idx]
            b = mezclados[idx + 1] if idx + 1 < len(mezclados) else None
            pares.append({
                "posicion": idx // 2 + 1,
                "competidor_a": a,
                "competidor_b": b,   # None = BYE
                "es_bye": b is None,
                # Advertencia si hay gran diferencia de edad/peso (para modal local)
                "advertencia": _detectar_advertencia(a, b),
            })
        return pares

    def _detectar_advertencia(a, b):
        if not b:
            return None
        advertencias = []
        if a.get("edad") and b.get("edad"):
            diff_edad = abs(a["edad"] - b["edad"])
            if diff_edad >= 2:
                advertencias.append(f"Diferencia de edad: {diff_edad} años")
        if a.get("peso") and b.get("peso"):
            diff_peso = abs(a["peso"] - b["peso"])
            if diff_peso >= 10:
                advertencias.append(f"Diferencia de peso: {diff_peso:.1f} kg")
        return " | ".join(advertencias) if advertencias else None

    # Agrupar por categoría
    por_cat: dict = {}
    for p in enriquecidos:
        cid = p["idcategoria"] or 0
        por_cat.setdefault(cid, []).append(p)

    resultado = []
    for cid, participantes in por_cat.items():
        cat_res = db.table("torneo_categorias").select("nombre_categoria")\
            .eq("idcategoria", cid).execute()
        nombre_cat = cat_res.data[0]["nombre_categoria"] if cat_res.data else f"Categoría {cid}"
        resultado.append({
            "idcategoria":     cid,
            "nombre_categoria": nombre_cat,
            "total":           len(participantes),
            "enfrentamientos": _emparejar_preview(participantes),
        })

    return {
        "ok":        True,
        "idtorneo":  idtorneo,
        "categorias": resultado,
        "nota": "Estos son emparejamientos SUGERIDOS. Usa el endpoint de reasignar para editarlos antes de confirmar.",
    }


@router.put("/torneos/{idtorneo}/matchmaking/reasignar",
            summary="Intercambiar dos competidores entre sí (matchmaking editable)")
async def reasignar_matchmaking(
    idtorneo: int,
    body: ReasignarMatchmaking,
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Intercambia las posiciones de dos competidores en el bracket antes de confirmar.
    Busca los combates donde están asignados y los intercambia.
    """
    _require_roles(user, ["SuperAdmin"])

    # Buscar combate de A
    c_a = db.table("combates").select("idcombate, id_competidor_1, id_competidor_2")\
        .eq("idtorneo", idtorneo).eq("ronda", 1)\
        .or_(
            f"id_competidor_1.eq.{body.idinscripcion_a},"
            f"id_competidor_2.eq.{body.idinscripcion_a}"
        ).execute()

    # Buscar combate de B
    c_b = db.table("combates").select("idcombate, id_competidor_1, id_competidor_2")\
        .eq("idtorneo", idtorneo).eq("ronda", 1)\
        .or_(
            f"id_competidor_1.eq.{body.idinscripcion_b},"
            f"id_competidor_2.eq.{body.idinscripcion_b}"
        ).execute()

    if not c_a.data:
        raise HTTPException(404, f"Competidor {body.idinscripcion_a} no tiene combate asignado")
    if not c_b.data:
        raise HTTPException(404, f"Competidor {body.idinscripcion_b} no tiene combate asignado")

    ca = c_a.data[0]
    cb = c_b.data[0]

    # Determinar en qué slot está cada uno y hacer el intercambio
    # Competidor A → va al slot de B
    if ca["id_competidor_1"] == body.idinscripcion_a:
        db.table("combates").update({"id_competidor_1": body.idinscripcion_b})\
            .eq("idcombate", ca["idcombate"]).execute()
    else:
        db.table("combates").update({"id_competidor_2": body.idinscripcion_b})\
            .eq("idcombate", ca["idcombate"]).execute()

    # Competidor B → va al slot de A
    if cb["id_competidor_1"] == body.idinscripcion_b:
        db.table("combates").update({"id_competidor_1": body.idinscripcion_a})\
            .eq("idcombate", cb["idcombate"]).execute()
    else:
        db.table("combates").update({"id_competidor_2": body.idinscripcion_a})\
            .eq("idcombate", cb["idcombate"]).execute()

    return {
        "ok":      True,
        "mensaje": f"Competidores {body.idinscripcion_a} y {body.idinscripcion_b} intercambiados correctamente",
    }


@router.post("/torneos/{idtorneo}/areas/{idarea}/asignar-combate/{idcombate}",
             summary="Asignar un combate a un área específica")
async def asignar_combate_a_area(
    idtorneo:  int,
    idarea:    int,
    idcombate: int,
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _require_roles(user, ["SuperAdmin", "Staff"])

    # Verificar área y combate
    area = db.table("areas_combate").select("*")\
        .eq("idarea", idarea).eq("idtorneo", idtorneo).execute()
    if not area.data:
        raise HTTPException(404, "Área no encontrada en este torneo")

    combate = db.table("combates").select("*")\
        .eq("idcombate", idcombate).eq("idtorneo", idtorneo).execute()
    if not combate.data:
        raise HTTPException(404, "Combate no encontrado en este torneo")

    if combate.data[0].get("estatus") == "finalizado":
        raise HTTPException(400, "No se puede reasignar un combate ya finalizado")

    # Asignar el juez del área al combate también
    juez_area = area.data[0].get("idjuez_asignado")

    db.table("combates").update({
        "idarea":   idarea,
        "id_juez":  juez_area,
    }).eq("idcombate", idcombate).execute()

    # Actualizar las inscripciones de los competidores con el área asignada
    c = combate.data[0]
    for idinsc in [c.get("id_competidor_1"), c.get("id_competidor_2")]:
        if idinsc:
            db.table("inscripciones_torneo")\
                .update({"idarea_asignada": idarea})\
                .eq("idinscripcion", idinsc).execute()

    return {
        "ok":      True,
        "mensaje": f"Combate {idcombate} asignado a {area.data[0]['nombre_area']}",
        "idarea":  idarea,
        "idjuez":  juez_area,
    }


@router.post("/torneos/{idtorneo}/matchmaking/confirmar",
             summary="Confirmar matchmaking y guardar combates en BD")
async def matchmaking_confirmar(
    idtorneo: int,
    db:   Client = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Genera y guarda en la tabla combates todos los enfrentamientos
    del matchmaking preview. Si ya existen combates pendientes los elimina
    y los regenera para que siempre se parta de un estado limpio.
    """
    _require_roles(user, ["SuperAdmin"])

    # ── 1. Verificar torneo ──────────────────────────────────
    torneo_res = db.table("torneos").select("idtorneo, tipo_torneo, estatus")\
        .eq("idtorneo", idtorneo).execute()
    if not torneo_res.data:
        raise HTTPException(404, "Torneo no encontrado")
    torneo = torneo_res.data[0]
    if torneo["estatus"] not in (2, "en_curso", "activo"):
        raise HTTPException(400, "El torneo debe estar en curso para confirmar el matchmaking")

    # ── 2. Traer asistentes pagados con check-in ─────────────
    asistentes_res = db.table("inscripciones_torneo").select(
        "idinscripcion, idcategoria, idescuela, peso_declarado, peso_bascula, "
        "alumnos(nombres, apellidopaterno)"
    ).eq("idtorneo", idtorneo)\
     .eq("estatus_checkin", True)\
     .or_("estatus_pago.eq.Pagado,estatus_pago.eq.pagado")\
     .execute()

    asistentes = asistentes_res.data or []
    if not asistentes:
        raise HTTPException(400, "No hay competidores con check-in para generar combates")

    # ── 3. Eliminar combates pendientes anteriores del torneo ─
    db.table("combates")\
        .delete()\
        .eq("idtorneo", idtorneo)\
        .eq("estatus", "pendiente")\
        .execute()

    # ── 4. Agrupar por categoría ─────────────────────────────
    por_cat: dict = {}
    for a in asistentes:
        cid = a.get("idcategoria") or 0
        por_cat.setdefault(cid, []).append(a)

    # ── 5. Generar combates mezclando escuelas ───────────────
    def _mezclar_por_escuela(participantes):
        por_escuela: dict = {}
        for p in participantes:
            eid = p.get("idescuela", 0)
            por_escuela.setdefault(eid, []).append(p)
        mezclados = []
        listas = list(por_escuela.values())
        i = 0
        while any(listas):
            bucket = listas[i % len(listas)]
            if bucket:
                mezclados.append(bucket.pop(0))
            i += 1
        return mezclados

    combates_creados = []
    total_combates   = 0

    for idcategoria, participantes in por_cat.items():
        mezclados = _mezclar_por_escuela(participantes)

        for idx in range(0, len(mezclados), 2):
            a = mezclados[idx]
            b = mezclados[idx + 1] if idx + 1 < len(mezclados) else None

            nuevo_combate = {
                "idtorneo":         idtorneo,
                "idcategoria":      idcategoria if idcategoria != 0 else None,
                "id_competidor_1":  a["idinscripcion"],
                "id_competidor_2":  b["idinscripcion"] if b else None,
                "ronda":            1,
                "estatus":          "pendiente",
                "es_bye":           b is None,
            }

            res = db.table("combates").insert(nuevo_combate).execute()
            if res.data:
                idcombate = res.data[0]["idcombate"]
                combates_creados.append({
                    "idcombate":       idcombate,
                    "idcategoria":     idcategoria,
                    "competidor_a":    f"{a['alumnos']['nombres']} {a['alumnos']['apellidopaterno']}".strip() if a.get("alumnos") else str(a["idinscripcion"]),
                    "competidor_b":    f"{b['alumnos']['nombres']} {b['alumnos']['apellidopaterno']}".strip() if b and b.get("alumnos") else ("BYE" if not b else str(b["idinscripcion"])),
                    "es_bye":          b is None,
                })
                total_combates += 1

    return {
        "ok":             True,
        "idtorneo":       idtorneo,
        "total_combates": total_combates,
        "combates":       combates_creados,
        "mensaje":        f"✅ {total_combates} combates generados y guardados correctamente",
    }