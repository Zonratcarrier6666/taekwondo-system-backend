# ============================================================
#  app/routers/brackets.py
#  Brackets de eliminación simple en tiempo real
#  Flujo: cerrar_checkin → genera categorías + ronda 1
#         juez registra resultado → sistema avanza ganador
# ============================================================

import math
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional as Opt
from supabase import Client

from utils.database   import get_db
from utils.auth_utils import get_current_user

router = APIRouter(prefix="/brackets", tags=["Torneos y Competencias"])

# ─── Auth opcional para endpoints públicos ───────────────────
from fastapi.security import HTTPBearer as _HTTPBearer, HTTPAuthorizationCredentials as _Creds
from jose import jwt as _jwt, JWTError as _JWTErr
import os as _os

_SECRET  = _os.getenv("JWT_SECRET_KEY", "tu_llave_secreta_super_segura_123")
_bearer  = _HTTPBearer(auto_error=False)

async def _get_optional_user(creds: Opt[_Creds] = Depends(_bearer)) -> Opt[dict]:
    """Devuelve el usuario si hay token válido, o None si no hay token."""
    if not creds:
        return None
    try:
        payload = _jwt.decode(creds.credentials, _SECRET, algorithms=["HS256"])
        return {"username": payload.get("sub"), "rol": payload.get("role"), "idusuario": payload.get("id")}
    except _JWTErr:
        return None


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def _calcular_edad(fecha_nac: str) -> int:
    from datetime import date
    try:
        fn  = date.fromisoformat(str(fecha_nac)[:10])
        hoy = date.today()
        return hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
    except:
        return 0

def _require_roles(user: dict, roles: list):
    if user.get("rol") not in roles:
        raise HTTPException(403, "Sin acceso para esta operación")

def _siguiente_potencia_2(n: int) -> int:
    """Devuelve la siguiente potencia de 2 >= n (para el bracket)."""
    if n <= 1: return 1
    return 2 ** math.ceil(math.log2(n))

def _nombre_ronda(ronda: int, total_rondas: int) -> str:
    restantes = total_rondas - ronda + 1
    if restantes == 1: return "Final"
    if restantes == 2: return "Semifinal"
    if restantes == 3: return "Cuartos de Final"
    return f"Ronda {ronda}"


# ─────────────────────────────────────────────────────────────
#  LÓGICA DE EMPAREJAMIENTO
# ─────────────────────────────────────────────────────────────

def _emparejar(participantes: list[dict]) -> list[tuple]:
    """
    Empareja participantes minimizando enfrentamientos del mismo dojo en R1.
    Devuelve lista de tuplas (a, b) donde b puede ser None (BYE).
    """
    # Separar por escuela e intercalar
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

    # Rellenar hasta potencia de 2 con BYEs
    n     = len(mezclados)
    slots = _siguiente_potencia_2(n)
    byes  = slots - n
    for _ in range(byes):
        mezclados.append(None)   # None = BYE

    # Generar pares
    pares = []
    for idx in range(0, slots, 2):
        pares.append((mezclados[idx], mezclados[idx + 1]))
    return pares


# ─────────────────────────────────────────────────────────────
#  1. CERRAR CHECK-IN Y GENERAR BRACKETS
# ─────────────────────────────────────────────────────────────

@router.post("/torneos/{idtorneo}/cerrar-checkin",
             summary="Cerrar asistencia y generar brackets automáticamente")
async def cerrar_checkin_y_generar(
    idtorneo: int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["SuperAdmin"])

    # Verificar torneo
    t = db.table("torneos").select("*").eq("idtorneo", idtorneo).execute()
    if not t.data:
        raise HTTPException(404, "Torneo no encontrado")

    # Traer solo los que hicieron check-in (asistio=True o qr_usado=True)
    insc_res = db.table("inscripciones_torneo").select(
        "idinscripcion, idalumno, idcategoria, peso_declarado, idescuela, "
        "alumnos(nombres, apellidopaterno, fechanacimiento, idescuela)"
    ).eq("idtorneo", idtorneo).eq("qr_usado", True)\
     .eq("estatus_pago", "pagado").execute()

    asistentes = insc_res.data or []
    if len(asistentes) < 2:
        raise HTTPException(400, "Se necesitan al menos 2 asistentes para generar brackets")

    # Traer categorías del torneo
    cats_res = db.table("torneo_categorias").select("*")\
        .eq("idtorneo", idtorneo).execute()
    categorias = cats_res.data or []

    if not categorias:
        raise HTTPException(400,
            "El torneo no tiene categorías definidas. "
            "Agrega categorías en torneo_categorias antes de cerrar el check-in."
        )

    # Juez del torneo (guardado en torneos.modalidades o asignado)
    id_juez = t.data[0].get("id_juez")

    resumen = []
    combates_creados = 0

    for cat in categorias:
        idcategoria = cat["idcategoria"]

        # Filtrar asistentes que pertenecen a esta categoría
        # Si el alumno ya tiene idcategoria asignado, usarlo
        # Si no, asignar automáticamente según los requisitos de la categoría
        en_categoria = []
        sin_categoria = []

        for insc in asistentes:
            if insc.get("idcategoria") == idcategoria:
                en_categoria.append(insc)
            elif not insc.get("idcategoria"):
                sin_categoria.append(insc)

        # Auto-asignar alumnos sin categoría si cumplen requisitos
        for insc in sin_categoria:
            al   = insc.get("alumnos") or {}
            edad = _calcular_edad(al.get("fechanacimiento", ""))
            peso = insc.get("peso_declarado")

            cumple = True
            if cat.get("edad_min") and edad < cat["edad_min"]: cumple = False
            if cat.get("edad_max") and edad > cat["edad_max"]: cumple = False
            if cat.get("peso_min") and peso and peso < cat["peso_min"]: cumple = False
            if cat.get("peso_max") and peso and peso > cat["peso_max"]: cumple = False

            if cumple:
                en_categoria.append(insc)
                # Actualizar la inscripción con la categoría
                db.table("inscripciones_torneo").update({"idcategoria": idcategoria})\
                    .eq("idinscripcion", insc["idinscripcion"]).execute()

        if len(en_categoria) < 2:
            resumen.append({
                "idcategoria":  idcategoria,
                "nombre":       cat["nombre_categoria"],
                "participantes": len(en_categoria),
                "combates":     0,
                "nota":         "Categoría omitida — menos de 2 participantes",
            })
            continue

        # Limpiar combates anteriores de ronda 1 si se regenera
        db.table("combates").delete()\
            .eq("idtorneo", idtorneo)\
            .eq("idcategoria", idcategoria)\
            .eq("ronda", 1).execute()

        # Generar emparejamientos
        pares = _emparejar(en_categoria)
        total_rondas = int(math.log2(_siguiente_potencia_2(len(en_categoria))))

        combates_cat = []
        for pos, (a, b) in enumerate(pares, start=1):
            combate = {
                "idtorneo":          idtorneo,
                "idcategoria":       idcategoria,
                "ronda":             1,
                "bracket_posicion":  pos,
                "id_competidor_1":   a["idinscripcion"] if a else None,
                "id_competidor_2":   b["idinscripcion"] if b else None,
                "es_bye":            b is None,
                "estatus":           "bye" if b is None else "pendiente",
                "id_juez":           id_juez,
                "puntos_c1":         0,
                "puntos_c2":         0,
            }
            combates_cat.append(combate)

        # Insertar todos los combates de ronda 1
        db.table("combates").insert(combates_cat).execute()

        # Si hay BYEs, avanzar automáticamente al competidor único
        for combate in combates_cat:
            if combate["es_bye"] and combate["id_competidor_1"]:
                _avanzar_ganador(
                    idtorneo, idcategoria,
                    ronda_actual=1,
                    posicion_actual=combate["bracket_posicion"],
                    ganador_idinscripcion=combate["id_competidor_1"],
                    total_rondas=total_rondas,
                    db=db,
                    id_juez=id_juez,
                )

        combates_creados += len(combates_cat)

        # Marcar categoría como bracket generado
        db.table("torneo_categorias").update({"bracket_generado": True})\
            .eq("idcategoria", idcategoria).execute()

        resumen.append({
            "idcategoria":   idcategoria,
            "nombre":        cat["nombre_categoria"],
            "participantes": len(en_categoria),
            "combates_r1":   len(combates_cat),
            "total_rondas":  total_rondas,
            "byes":          sum(1 for _, b in pares if b is None),
        })

    # Actualizar estatus del torneo a "en_curso" (estatus=2)
    db.table("torneos").update({"estatus": 2}).eq("idtorneo", idtorneo).execute()

    return {
        "ok":              True,
        "mensaje":         "Check-in cerrado y brackets generados.",
        "combates_creados": combates_creados,
        "categorias":      resumen,
    }


# ─────────────────────────────────────────────────────────────
#  2. ASIGNAR JUEZ AL TORNEO
# ─────────────────────────────────────────────────────────────

@router.post("/torneos/{idtorneo}/asignar-juez/{idusuario}",
             summary="Asignar juez único al torneo")
async def asignar_juez(
    idtorneo:  int,
    idusuario: int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["SuperAdmin"])

    # Verificar que el usuario existe y es Juez
    u = db.table("usuarios").select("idusuario, username, rol")\
        .eq("idusuario", idusuario).execute()
    if not u.data:
        raise HTTPException(404, "Usuario no encontrado")
    if u.data[0].get("rol") not in ["Juez", "SuperAdmin"]:
        raise HTTPException(400, "El usuario debe tener rol Juez o SuperAdmin")

    # Guardar en torneos.modalidades como id_juez
    t = db.table("torneos").select("modalidades").eq("idtorneo", idtorneo).execute()
    if not t.data:
        raise HTTPException(404, "Torneo no encontrado")

    # Usar columna id_juez (la agregamos en migración)
    db.table("torneos").update({"id_juez": idusuario}).eq("idtorneo", idtorneo).execute()

    # Actualizar todos los combates existentes del torneo
    db.table("combates").update({"id_juez": idusuario}).eq("idtorneo", idtorneo).execute()

    return {
        "ok":      True,
        "mensaje": f"Juez {u.data[0]['username']} asignado al torneo.",
        "juez":    u.data[0],
    }


# ─────────────────────────────────────────────────────────────
#  3. REGISTRAR RESULTADO DE COMBATE
# ─────────────────────────────────────────────────────────────

def _avanzar_ganador(
    idtorneo: int, idcategoria: int,
    ronda_actual: int, posicion_actual: int,
    ganador_idinscripcion: int,
    total_rondas: int,
    db: Client,
    id_juez: Optional[int] = None,
):
    """
    Avanza al ganador al siguiente combate del bracket.
    posicion_actual determina en qué slot de la siguiente ronda entra.
    """
    siguiente_ronda = ronda_actual + 1
    if siguiente_ronda > total_rondas:
        return   # Ya es campeón, no hay siguiente ronda

    # Posición en la siguiente ronda: pares adyacentes se fusionan
    siguiente_pos = math.ceil(posicion_actual / 2)

    # Buscar si ya existe el combate de la siguiente ronda en esa posición
    combate_sig = db.table("combates").select("*")\
        .eq("idtorneo", idtorneo)\
        .eq("idcategoria", idcategoria)\
        .eq("ronda", siguiente_ronda)\
        .eq("bracket_posicion", siguiente_pos).execute()

    if combate_sig.data:
        # El combate ya existe, llenar el slot vacío
        c = combate_sig.data[0]
        if not c.get("id_competidor_1"):
            db.table("combates").update({"id_competidor_1": ganador_idinscripcion})\
                .eq("idcombate", c["idcombate"]).execute()
        else:
            db.table("combates").update({"id_competidor_2": ganador_idinscripcion})\
                .eq("idcombate", c["idcombate"]).execute()
    else:
        # Crear el combate de la siguiente ronda
        db.table("combates").insert({
            "idtorneo":         idtorneo,
            "idcategoria":      idcategoria,
            "ronda":            siguiente_ronda,
            "bracket_posicion": siguiente_pos,
            "id_competidor_1":  ganador_idinscripcion,
            "id_competidor_2":  None,
            "es_bye":           False,
            "estatus":          "pendiente",
            "id_juez":          id_juez,
            "puntos_c1":        0,
            "puntos_c2":        0,
        }).execute()


@router.post("/combates/{idcombate}/resultado",
             summary="Juez registra resultado del combate")
async def registrar_resultado(
    idcombate: int,
    puntos_c1:  int,
    puntos_c2:  int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["Juez", "SuperAdmin"])

    # Obtener combate
    c_res = db.table("combates").select("*").eq("idcombate", idcombate).execute()
    if not c_res.data:
        raise HTTPException(404, "Combate no encontrado")
    c = c_res.data[0]

    if c.get("estatus") == "finalizado":
        raise HTTPException(400, "Este combate ya fue finalizado")
    if not c.get("id_competidor_1") or not c.get("id_competidor_2"):
        raise HTTPException(400, "El combate no tiene dos competidores asignados")
    if puntos_c1 == puntos_c2:
        raise HTTPException(400, "No puede haber empate en Taekwondo. Revisa los puntos.")

    # Determinar ganador
    ganador_id = c["id_competidor_1"] if puntos_c1 > puntos_c2 else c["id_competidor_2"]

    # Actualizar combate
    db.table("combates").update({
        "puntos_c1":    puntos_c1,
        "puntos_c2":    puntos_c2,
        "id_ganador":   ganador_id,
        "estatus":      "finalizado",
        "tiempo_fin":   datetime.now().isoformat(),
    }).eq("idcombate", idcombate).execute()

    # Calcular total de rondas REAL — basado en participantes inscritos de la categoría
    inscritos_cat = db.table("inscripciones_torneo").select("idinscripcion")\
        .eq("idtorneo", c["idtorneo"])\
        .eq("idcategoria", c["idcategoria"])\
        .eq("estatus_pago", "pagado").execute()
    n_participantes = len(inscritos_cat.data) if inscritos_cat.data else 2
    total_rondas = int(math.log2(_siguiente_potencia_2(max(n_participantes, 2))))

    # Avanzar ganador a la siguiente ronda
    _avanzar_ganador(
        idtorneo=c["idtorneo"],
        idcategoria=c["idcategoria"],
        ronda_actual=c["ronda"],
        posicion_actual=c["bracket_posicion"],
        ganador_idinscripcion=ganador_id,
        total_rondas=total_rondas,
        db=db,
        id_juez=c.get("id_juez"),
    )

    # Verificar si esta era la final
    es_final = not db.table("combates").select("idcombate")\
        .eq("idtorneo", c["idtorneo"])\
        .eq("idcategoria", c["idcategoria"])\
        .eq("estatus", "pendiente").execute().data

    campeón = None
    if es_final:
        # Obtener datos del campeón
        champ = db.table("inscripciones_torneo").select(
            "idinscripcion, alumnos(nombres, apellidopaterno)"
        ).eq("idinscripcion", ganador_id).execute()
        if champ.data:
            al = champ.data[0].get("alumnos") or {}
            campeón = f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip()

    # Obtener datos de los competidores para el response
    def _nombre_insc(idinsc):
        r = db.table("inscripciones_torneo").select(
            "alumnos(nombres, apellidopaterno)"
        ).eq("idinscripcion", idinsc).execute()
        if r.data:
            al = r.data[0].get("alumnos") or {}
            return f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip()
        return "Desconocido"

    return {
        "ok":           True,
        "idcombate":    idcombate,
        "puntos_c1":    puntos_c1,
        "puntos_c2":    puntos_c2,
        "ganador_id":   ganador_id,
        "ganador_nombre": _nombre_insc(ganador_id),
        "es_final":     es_final,
        "campeon":      campeón,
        "mensaje":      f"🏆 ¡{campeón} es el campeón de la categoría!" if campeón else "Resultado registrado. Ganador avanzado a siguiente ronda.",
    }


# ─────────────────────────────────────────────────────────────
#  5. BRACKET LIVE — todos los brackets del torneo
# ─────────────────────────────────────────────────────────────

@router.get("/torneos/{idtorneo}/bracket/live",
            summary="Todos los brackets del torneo en tiempo real")
async def bracket_live(
    idtorneo: int,
    db: Client = Depends(get_db),
    _user: Opt[dict] = Depends(_get_optional_user),
):
    """
    Endpoint público (sin auth) para que el frontend
    pinte todos los brackets en tiempo real.
    Llama a este endpoint cada 10-15 segundos para actualizar.
    """
    # Obtener categorías con brackets generados
    cats = db.table("torneo_categorias").select("*")\
        .eq("idtorneo", idtorneo)\
        .eq("bracket_generado", True).execute().data or []

    if not cats:
        return {"ok": True, "idtorneo": idtorneo, "categorias": [], "mensaje": "Sin brackets generados aún"}

    # Obtener todos los combates del torneo de una sola query
    combates_res = db.table("combates").select(
        "idcombate, idcategoria, ronda, bracket_posicion, estatus, es_bye, "
        "id_competidor_1, id_competidor_2, id_ganador, "
        "puntos_c1, puntos_c2, area_asignada, tiempo_inicio, tiempo_fin"
    ).eq("idtorneo", idtorneo)\
     .order("ronda").order("bracket_posicion").execute().data or []

    # Agrupar combates por categoría
    por_categoria: dict = {}
    for c in combates_res:
        cat_id = c["idcategoria"]
        por_categoria.setdefault(cat_id, []).append(c)

    # Obtener todos los competidores de una sola query (evitar N+1)
    insc_ids = set()
    for c in combates_res:
        if c.get("id_competidor_1"): insc_ids.add(c["id_competidor_1"])
        if c.get("id_competidor_2"): insc_ids.add(c["id_competidor_2"])
        if c.get("id_ganador"):      insc_ids.add(c["id_ganador"])

    competidores: dict = {}
    if insc_ids:
        insc_res = db.table("inscripciones_torneo").select(
            "idinscripcion, peso_declarado, "
            "alumnos(nombres, apellidopaterno, fechanacimiento, "
            "cintasgrados(nivelkupdan, color)), "
            "datosescuela!inscripciones_torneo_idescuela_fkey(nombreescuela)"
        ).in_("idinscripcion", list(insc_ids)).execute().data or []

        for insc in insc_res:
            al  = insc.get("alumnos") or {}
            cg  = al.get("cintasgrados") or {}
            esc = insc.get("datosescuela") or {}
            competidores[insc["idinscripcion"]] = {
                "idinscripcion": insc["idinscripcion"],
                "nombre":        f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip(),
                "edad":          _calcular_edad(al.get("fechanacimiento", "")),
                "cinta":         cg.get("nivelkupdan", ""),
                "color_cinta":   cg.get("color", ""),
                "peso":          insc.get("peso_declarado"),
                "escuela":       esc.get("nombreescuela", ""),
            }

    def _get_comp(idinsc):
        return competidores.get(idinsc) if idinsc else None

    # Armar respuesta por categoría
    resultado_cats = []
    for cat in cats:
        cid      = cat["idcategoria"]
        combates = por_categoria.get(cid, [])
        if not combates:
            continue

        rondas: dict = {}
        total_rondas = max((c["ronda"] for c in combates), default=1)

        for c in combates:
            r = c["ronda"]
            rondas.setdefault(r, []).append({
                "idcombate":        c["idcombate"],
                "bracket_posicion": c["bracket_posicion"],
                "nombre_ronda":     _nombre_ronda(r, total_rondas),
                "estatus":          c.get("estatus", "pendiente"),
                "es_bye":           c.get("es_bye", False),
                "competidor_1":     _get_comp(c.get("id_competidor_1")),
                "competidor_2":     _get_comp(c.get("id_competidor_2")),
                "puntos_c1":        c.get("puntos_c1", 0),
                "puntos_c2":        c.get("puntos_c2", 0),
                "ganador":          _get_comp(c.get("id_ganador")),
                "area_asignada":    c.get("area_asignada"),
                "tiempo_fin":       c.get("tiempo_fin"),
            })

        # Campeón
        final = next(
            (c for c in combates if c["ronda"] == total_rondas and c.get("id_ganador")),
            None
        )

        resultado_cats.append({
            "idcategoria":  cid,
            "nombre":       cat["nombre_categoria"],
            "finalizados":  sum(1 for c in combates if c.get("estatus") == "finalizado"),
            "pendientes":   sum(1 for c in combates if c.get("estatus") == "pendiente"),
            "campeon":      _get_comp(final["id_ganador"]) if final else None,
            "rondas": [
                {
                    "ronda":       r,
                    "nombre_ronda": _nombre_ronda(r, total_rondas),
                    "combates":    rondas[r],
                }
                for r in sorted(rondas.keys())
            ],
        })

    return {
        "ok":           True,
        "idtorneo":     idtorneo,
        "total_categorias": len(resultado_cats),
        "categorias":   resultado_cats,
        "timestamp":    datetime.now().isoformat(),
    }


# ─────────────────────────────────────────────────────────────
#  4. VER BRACKET POR CATEGORÍA
# ─────────────────────────────────────────────────────────────

def _fmt_competidor(idinscripcion: Optional[int], db: Client) -> Optional[dict]:
    if not idinscripcion:
        return None
    r = db.table("inscripciones_torneo").select(
        "idinscripcion, peso_declarado, idescuela, "
        "alumnos(nombres, apellidopaterno, fechanacimiento, "
        "cintasgrados(nivelkupdan, color)), "
        "datosescuela!inscripciones_torneo_idescuela_fkey(nombreescuela)"
    ).eq("idinscripcion", idinscripcion).execute()
    if not r.data:
        return None
    insc = r.data[0]
    al   = insc.get("alumnos") or {}
    cg   = al.get("cintasgrados") or {}
    esc  = insc.get("datosescuela") or {}
    return {
        "idinscripcion": idinscripcion,
        "nombre":        f"{al.get('nombres','')} {al.get('apellidopaterno','')}".strip(),
        "edad":          _calcular_edad(al.get("fechanacimiento", "")),
        "cinta":         cg.get("nivelkupdan", ""),
        "color_cinta":   cg.get("color", ""),
        "peso":          insc.get("peso_declarado"),
        "escuela":       esc.get("nombreescuela", ""),
    }


@router.get("/torneos/{idtorneo}/bracket/{idcategoria}",
            summary="Ver bracket completo de una categoría")
async def ver_bracket(
    idtorneo:    int,
    idcategoria: int,
    db:   Client = Depends(get_db),
    _user: Opt[dict] = Depends(_get_optional_user),
):
    # Obtener todos los combates de esta categoría ordenados
    combates_res = db.table("combates").select("*")\
        .eq("idtorneo", idtorneo)\
        .eq("idcategoria", idcategoria)\
        .order("ronda").order("bracket_posicion").execute()

    if not combates_res.data:
        raise HTTPException(404, "No hay combates generados para esta categoría")

    combates = combates_res.data

    # Obtener info de la categoría
    cat_res = db.table("torneo_categorias").select("*")\
        .eq("idcategoria", idcategoria).execute()
    cat = cat_res.data[0] if cat_res.data else {}

    # Agrupar por ronda
    rondas: dict = {}
    for c in combates:
        r = c["ronda"]
        if r not in rondas:
            rondas[r] = []

        total_rondas = max(x["ronda"] for x in combates)

        rondas[r].append({
            "idcombate":       c["idcombate"],
            "bracket_posicion": c["bracket_posicion"],
            "nombre_ronda":    _nombre_ronda(r, total_rondas),
            "estatus":         c.get("estatus", "pendiente"),
            "es_bye":          c.get("es_bye", False),
            "competidor_1":    _fmt_competidor(c.get("id_competidor_1"), db),
            "competidor_2":    _fmt_competidor(c.get("id_competidor_2"), db),
            "puntos_c1":       c.get("puntos_c1", 0),
            "puntos_c2":       c.get("puntos_c2", 0),
            "ganador":         _fmt_competidor(c.get("id_ganador"), db) if c.get("id_ganador") else None,
            "area_asignada":   c.get("area_asignada"),
            "tiempo_inicio":   c.get("tiempo_inicio"),
            "tiempo_fin":      c.get("tiempo_fin"),
        })

    # Campeón (ganador del último combate finalizado de la última ronda)
    ultima_ronda  = max(rondas.keys())
    combate_final = next(
        (c for c in combates if c["ronda"] == ultima_ronda and c.get("id_ganador")),
        None
    )
    campeon = _fmt_competidor(combate_final["id_ganador"], db) if combate_final else None

    # Stats de la categoría
    total   = len(combates)
        
    return {
        "ok":         True,
        "idtorneo":   idtorneo,
        "categoria":  {
            "idcategoria":     idcategoria,
            "nombre":          cat.get("nombre_categoria", ""),
            "edad_min":        cat.get("edad_min"),
            "edad_max":        cat.get("edad_max"),
            "peso_min":        cat.get("peso_min"),
            "peso_max":        cat.get("peso_max"),
            "genero":          cat.get("genero"),
        },
        "resumen": {
            "total_combates":      total,
            "finalizados":         sum(1 for c in combates if c.get("estatus") == "finalizado"),
            "pendientes":          sum(1 for c in combates if c.get("estatus") == "pendiente"),
            "total_rondas":        max(rondas.keys()),
        },
        "campeon":    campeon,
        "rondas":     [
            {
                "ronda":          r,
                "nombre_ronda":   _nombre_ronda(r, max(rondas.keys())),
                "combates":       rondas[r],
            }
            for r in sorted(rondas.keys())
        ],
    }


# ─────────────────────────────────────────────────────────────
#  6. MIS COMBATES (vista del Juez)
# ─────────────────────────────────────────────────────────────

@router.get("/torneos/{idtorneo}/mis-combates",
            summary="Combates asignados al juez logueado")
async def mis_combates(
    idtorneo: int,
    user: dict = Depends(get_current_user),
    db:   Client = Depends(get_db),
):
    _require_roles(user, ["Juez", "SuperAdmin"])

    combates_res = db.table("combates").select("*")\
        .eq("idtorneo", idtorneo)\
        .eq("id_juez", user.get("idusuario"))\
        .order("ronda").order("bracket_posicion").execute()

    combates = []
    for c in combates_res.data or []:
        total_r = db.table("combates").select("ronda")\
            .eq("idtorneo", idtorneo)\
            .eq("idcategoria", c["idcategoria"]).execute()
        max_r = max((x["ronda"] for x in total_r.data), default=1)

        combates.append({
            "idcombate":       c["idcombate"],
            "idcategoria":     c["idcategoria"],
            "ronda":           c["ronda"],
            "nombre_ronda":    _nombre_ronda(c["ronda"], max_r),
            "bracket_posicion": c["bracket_posicion"],
            "estatus":         c.get("estatus"),
            "es_bye":          c.get("es_bye", False),
            "competidor_1":    _fmt_competidor(c.get("id_competidor_1"), db),
            "competidor_2":    _fmt_competidor(c.get("id_competidor_2"), db),
            "ganador":         _fmt_competidor(c.get("id_ganador"), db) if c.get("id_ganador") else None,
            "puntos_c1":       c.get("puntos_c1", 0),
            "puntos_c2":       c.get("puntos_c2", 0),
            "area_asignada":   c.get("area_asignada"),
        })

    pendientes   = [c for c in combates if c["estatus"] == "pendiente"]
    finalizados  = [c for c in combates if c["estatus"] == "finalizado"]

    return {
        "ok":          True,
        "juez":        user.get("username"),
        "pendientes":  pendientes,
        "finalizados": finalizados,
        "total":       len(combates),
    }