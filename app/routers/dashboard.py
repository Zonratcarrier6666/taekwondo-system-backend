from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client
from datetime import datetime, timedelta, date
from typing import Optional
from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.dashboard import (
    DashboardEscuela, DashboardSuperAdmin, DashboardProfesor,
    BeltStat, FinanceStat, FinanceMes, AlumnoDeudaVencida,
    AsistenciaDia, ExamenProximo, TorneoProximo, AlumnoCumple,
    EscuelaResumen, EscuelaSimple, UsuarioItem,
    AlumnoAusente, PromocionGrado, AlumnoLista,
)

router = APIRouter(prefix="/dashboard", tags=["Estadísticas y Dashboard"])


# ─────────────────────────────────────────────────────────────
#  HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────

def _dias_semana() -> list[dict]:
    """Genera los últimos 7 días con label en español, value=0."""
    dias_es = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
    hoy = date.today()
    return [
        {
            "label": dias_es[(hoy - timedelta(days=6 - i)).weekday()],
            "dia": str(hoy - timedelta(days=6 - i)),
            "value": 0.0,
        }
        for i in range(7)
    ]


def _safe_float(val) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _safe_int(val) -> int:
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def _get_idescuela(user: dict, db: Client) -> int:
    """Resuelve el idescuela desde el JWT para Escuela o Profesor."""
    id_usuario = user.get("idusuario")
    rol = user.get("rol")

    if rol == "Escuela":
        res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if res.data:
            return res.data[0]["idescuela"]

    elif rol == "Profesor":
        res = db.table("profesores").select("idescuela").eq("idusuario", id_usuario).execute()
        if res.data:
            return res.data[0]["idescuela"]

    raise HTTPException(status_code=403, detail="No tienes una escuela asignada en tu perfil.")


def _get_cintas_escuela(id_escuela: int, db: Client) -> dict:
    """
    Devuelve un dict idgrado → datos de cinta, usando el catálogo
    propio de la escuela si existe, o el catálogo global como fallback.
    Incluye color, color_stripe, nivelkupdan y orden para renderizado exacto.
    """
    propias = db.table("cintasgrados")\
        .select("idgrado, nivelkupdan, color, color_stripe, orden")\
        .eq("idescuela", id_escuela)\
        .order("orden", nullsfirst=False)\
        .order("idgrado")\
        .execute()

    if propias.data:
        return {c["idgrado"]: c for c in propias.data}

    # Fallback catálogo global
    globales = db.table("cintasgrados")\
        .select("idgrado, nivelkupdan, color, color_stripe, orden")\
        .is_("idescuela", "null")\
        .order("idgrado")\
        .execute()

    return {c["idgrado"]: c for c in (globales.data or [])}


def _distribucion_cintas(alumnos: list, catalogo: dict) -> list:
    """
    Calcula la distribución de cintas agrupando por idgrado (no por color),
    enriqueciendo con datos completos del catálogo propio de la escuela.
    Respeta color_stripe para cintas con franja.
    """
    cintas_map: dict = {}
    sin_grado = 0

    for a in alumnos:
        idgrado = a.get("idgradoactual")
        if not idgrado:
            sin_grado += 1
            continue

        # Preferir datos del catálogo propio si existe
        cinta = catalogo.get(idgrado)
        if not cinta:
            # Intentar desde el join embebido
            g = a.get("grados") or {}
            if not g:
                sin_grado += 1
                continue
            cinta = {
                "idgrado":     idgrado,
                "nivelkupdan": g.get("nivelkupdan", ""),
                "color":       g.get("color", "Blanca"),
                "color_stripe": g.get("color_stripe"),
                "orden":       g.get("orden", idgrado),
            }

        key = idgrado  # agrupar por ID, no por color
        if key not in cintas_map:
            cintas_map[key] = {
                "idgrado":     cinta["idgrado"],
                "color":       cinta["color"],
                "color_stripe": cinta.get("color_stripe"),
                "nivelkupdan": cinta["nivelkupdan"],
                "orden":       cinta.get("orden") or cinta["idgrado"],
                "count":       0,
            }
        cintas_map[key]["count"] += 1

    # Ordenar por orden de la escuela
    resultado = sorted(cintas_map.values(), key=lambda x: x["orden"])

    # Agregar "Sin grado" si hay alumnos sin asignar
    if sin_grado:
        resultado.append({
            "idgrado": 0, "color": "Gris", "color_stripe": None,
            "nivelkupdan": "Sin grado", "orden": 9999, "count": sin_grado,
        })

    return resultado


# ─────────────────────────────────────────────────────────────
#  1. DASHBOARD ESCUELA
# ─────────────────────────────────────────────────────────────

@router.get("/escuela", response_model=DashboardEscuela)
async def get_school_stats(
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    id_escuela = _get_idescuela(user, db)

    hoy        = date.today()
    hace_7d    = str(hoy - timedelta(days=6))
    hace_30d   = str(hoy - timedelta(days=30))
    hace_7d_dt = datetime.now() - timedelta(days=7)

    # Inicio/fin de mes actual y anterior
    primer_dia_mes     = hoy.replace(day=1)
    ultimo_mes_inicio  = (primer_dia_mes - timedelta(days=1)).replace(day=1)
    ultimo_mes_fin     = primer_dia_mes - timedelta(days=1)

    # ── CONTEOS ────────────────────────────────────────────────
    alumnos_activos   = db.table("alumnos").select("idalumno", count="exact").eq("idescuela", id_escuela).eq("estatus", 1).execute()
    alumnos_inactivos = db.table("alumnos").select("idalumno", count="exact").eq("idescuela", id_escuela).eq("estatus", 0).execute()
    profesores        = db.table("profesores").select("idprofesor", count="exact").eq("idescuela", id_escuela).eq("estatus", 1).execute()

    total_activos   = _safe_int(alumnos_activos.count)
    total_inactivos = _safe_int(alumnos_inactivos.count)
    total_profes    = _safe_int(profesores.count)

    # ── FINANZAS ───────────────────────────────────────────────
    pagos_mes_actual = db.table("pagos").select("monto").eq("idescuela", id_escuela).eq("estatus", 1)\
        .gte("fecha_pago", str(primer_dia_mes)).execute()
    ingresos_mes_actual = sum(_safe_float(p["monto"]) for p in pagos_mes_actual.data)

    pagos_mes_anterior = db.table("pagos").select("monto").eq("idescuela", id_escuela).eq("estatus", 1)\
        .gte("fecha_pago", str(ultimo_mes_inicio)).lte("fecha_pago", str(ultimo_mes_fin)).execute()
    ingresos_mes_anterior = sum(_safe_float(p["monto"]) for p in pagos_mes_anterior.data)

    deuda_res = db.table("pagos").select("monto").eq("idescuela", id_escuela).eq("estatus", 0).execute()
    deuda_total = sum(_safe_float(p["monto"]) for p in deuda_res.data)

    pendientes_count = db.table("pagos").select("idpago", count="exact").eq("idescuela", id_escuela).eq("estatus", 0).execute()

    # ── INGRESOS ÚLTIMOS 7 DÍAS ────────────────────────────────
    pagos_semana = db.table("pagos").select("monto, fecha_pago").eq("idescuela", id_escuela)\
        .eq("estatus", 1).gte("fecha_pago", hace_7d).execute()

    semana_map = {d["dia"]: d for d in _dias_semana()}
    for p in pagos_semana.data:
        if p.get("fecha_pago"):
            dia_str = p["fecha_pago"][:10]
            if dia_str in semana_map:
                semana_map[dia_str]["value"] += _safe_float(p["monto"])

    ingresos_semana = [
        FinanceStat(label=v["label"], dia=v["dia"], value=round(v["value"], 2))
        for v in sorted(semana_map.values(), key=lambda x: x["dia"])
    ]

    # ── INGRESOS ÚLTIMOS 6 MESES ───────────────────────────────
    hace_6m = str((hoy.replace(day=1) - timedelta(days=150)).replace(day=1))
    pagos_6m = db.table("pagos").select("monto, fecha_pago").eq("idescuela", id_escuela)\
        .eq("estatus", 1).gte("fecha_pago", hace_6m).execute()

    meses_es = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
                7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}
    meses_map: dict = {}
    for p in pagos_6m.data:
        if p.get("fecha_pago"):
            d = datetime.fromisoformat(p["fecha_pago"][:10])
            key = f"{d.year}-{d.month:02d}"
            if key not in meses_map:
                meses_map[key] = {"mes_label": meses_es[d.month], "mes": key, "total": 0.0}
            meses_map[key]["total"] += _safe_float(p["monto"])

    ingresos_6_meses = [
        FinanceMes(mes_label=v["mes_label"], mes=v["mes"], total=round(v["total"], 2))
        for v in sorted(meses_map.values(), key=lambda x: x["mes"])
    ]

    # ── DISTRIBUCIÓN CINTAS ────────────────────────────────────
    catalogo_cintas = _get_cintas_escuela(id_escuela, db)
    cintas_res = db.table("alumnos")\
        .select("idalumno, idgradoactual, grados:cintasgrados(idgrado, color, color_stripe, nivelkupdan, orden)")\
        .eq("idescuela", id_escuela).eq("estatus", 1).execute()

    distribucion_cintas = [
        BeltStat(**{k: v for k, v in c.items() if k in ("idgrado","color","color_stripe","nivelkupdan","count")})
        for c in _distribucion_cintas(cintas_res.data, catalogo_cintas)
    ]

    # ── DEUDA VENCIDA (+30 días) ───────────────────────────────
    deuda_vencida_res = db.table("pagos")\
        .select("monto, concepto, fecharegistro, idalumno, alumnos(nombres, apellidopaterno)")\
        .eq("idescuela", id_escuela).eq("estatus", 0)\
        .lte("fecharegistro", hace_30d).execute()

    alumnos_deuda: list[AlumnoDeudaVencida] = []
    for p in deuda_vencida_res.data:
        al = p.get("alumnos") or {}
        dias = (hoy - datetime.fromisoformat(p["fecharegistro"][:10]).date()).days
        alumnos_deuda.append(AlumnoDeudaVencida(
            idalumno=p["idalumno"],
            nombres=al.get("nombres", ""),
            apellidopaterno=al.get("apellidopaterno", ""),
            monto=_safe_float(p["monto"]),
            concepto=p.get("concepto", ""),
            dias_vencido=dias,
        ))
    alumnos_deuda.sort(key=lambda x: x.dias_vencido, reverse=True)

    # ── PRÓXIMOS EXÁMENES ──────────────────────────────────────
    examenes_res = db.table("examenes").select("*")\
        .eq("idescuela", id_escuela).eq("estatus", 1)\
        .gte("fecha_programada", str(hoy))\
        .order("fecha_programada").limit(5).execute()

    proximos_examenes = [
        ExamenProximo(
            idexamen=e["idexamen"],
            nombre_examen=e["nombre_examen"],
            fecha_programada=str(e["fecha_programada"]),
            lugar=e.get("lugar"),
            costo_examen=_safe_float(e.get("costo_examen")),
            sinodal=e.get("sinodal"),
        )
        for e in examenes_res.data
    ]

    # ── ALUMNOS EN TORNEO ──────────────────────────────────────
    torneos_count = db.table("inscripciones_torneo")\
        .select("idinscripcion, alumnos!inner(idescuela)", count="exact")\
        .eq("alumnos.idescuela", id_escuela).execute()

    # ── ASISTENCIA ─────────────────────────────────────────────
    asistencia_hoy_res = db.table("asistencia").select("id", count="exact")\
        .eq("idescuela", id_escuela).eq("fecha", str(hoy)).eq("presente", True).execute()
    asistencia_hoy = _safe_int(asistencia_hoy_res.count)

    asistencia_semana_res = db.table("asistencia").select("fecha")\
        .eq("idescuela", id_escuela).eq("presente", True)\
        .gte("fecha", hace_7d).execute()

    asistencia_map = {d["dia"]: {"label": d["label"], "dia": d["dia"], "presentes": 0}
                      for d in _dias_semana()}
    for a in asistencia_semana_res.data:
        dia_str = str(a["fecha"])
        if dia_str in asistencia_map:
            asistencia_map[dia_str]["presentes"] += 1

    asistencia_semana = [
        AsistenciaDia(fecha=v["dia"], label=v["label"], presentes=v["presentes"])
        for v in sorted(asistencia_map.values(), key=lambda x: x["dia"])
    ]

    # ── ALUMNOS NUEVOS 30D ─────────────────────────────────────
    nuevos_res = db.table("alumnos").select("idalumno", count="exact")\
        .eq("idescuela", id_escuela).gte("fecharegistro", hace_30d).execute()

    # ── CUMPLEAÑOS PRÓXIMOS ────────────────────────────────────
    cumpleanos: list[AlumnoCumple] = []
    try:
        alumnos_cumple = db.table("alumnos")\
            .select("idalumno, nombres, apellidopaterno, fechanacimiento")\
            .eq("idescuela", id_escuela).eq("estatus", 1).execute()

        for a in alumnos_cumple.data:
            if not a.get("fechanacimiento"):
                continue
            try:
                fn = datetime.strptime(str(a["fechanacimiento"]), "%Y-%m-%d")
                cumple_este_anio = fn.replace(year=hoy.year).date()
                if hoy <= cumple_este_anio <= hoy + timedelta(days=7):
                    edad = hoy.year - fn.year
                    cumpleanos.append(AlumnoCumple(
                        idalumno=a["idalumno"],
                        nombres=a["nombres"],
                        apellidopaterno=a["apellidopaterno"],
                        fechanacimiento=str(a["fechanacimiento"]),
                        edad=edad,
                        fecha_display=fn.strftime("%d/%m"),
                    ))
            except ValueError:
                continue
    except Exception:
        pass

    return DashboardEscuela(
        total_alumnos_activos=total_activos,
        total_alumnos_inactivos=total_inactivos,
        total_profesores=total_profes,
        ingresos_mes_actual=round(ingresos_mes_actual, 2),
        ingresos_mes_anterior=round(ingresos_mes_anterior, 2),
        deuda_total_pendiente=round(deuda_total, 2),
        pagos_pendientes_count=_safe_int(pendientes_count.count),
        ingresos_semana=ingresos_semana,
        ingresos_6_meses=ingresos_6_meses,
        distribucion_cintas=distribucion_cintas,
        alumnos_deuda_vencida=alumnos_deuda[:10],
        proximos_examenes=proximos_examenes,
        alumnos_torneo_count=_safe_int(torneos_count.count),
        asistencia_hoy=asistencia_hoy,
        asistencia_semana=asistencia_semana,
        alumnos_nuevos_30d=_safe_int(nuevos_res.count),
        cumpleanos_proximos=cumpleanos,
        # Compatibilidad hacia atrás
        total_alumnos=total_activos,
        ingresos_semanales=sum(f.value for f in ingresos_semana),
        finanzas_semana=ingresos_semana,
        proximos_torneos=[],
    )


# ─────────────────────────────────────────────────────────────
#  2. DASHBOARD SUPERADMIN
# ─────────────────────────────────────────────────────────────

@router.get("/superadmin", response_model=DashboardSuperAdmin)
async def get_superadmin_stats(
    idescuela: Optional[int] = Query(None, description="Filtrar por escuela específica"),
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    if user.get("rol") != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Se requiere rol SuperAdmin.")

    hoy           = date.today()
    primer_dia_mes = hoy.replace(day=1)
    ultimo_mes_ini = (primer_dia_mes - timedelta(days=1)).replace(day=1)
    ultimo_mes_fin = primer_dia_mes - timedelta(days=1)
    hace_30d       = str(hoy - timedelta(days=30))
    hace_7d        = str(hoy - timedelta(days=7))
    hace_6m        = str((hoy.replace(day=1) - timedelta(days=150)).replace(day=1))

    # ── ESCUELAS ───────────────────────────────────────────────
    escuelas_res = db.table("datosescuela")\
        .select("idescuela, nombreescuela, logo_url, color_paleta").execute()
    todas_escuelas = escuelas_res.data or []

    # ── CONTEOS GLOBALES ───────────────────────────────────────
    alumnos_res   = db.table("alumnos").select("idalumno", count="exact").eq("estatus", 1).execute()
    profesores_res = db.table("profesores").select("idprofesor", count="exact").eq("estatus", 1).execute()

    # ── FINANZAS GLOBALES ──────────────────────────────────────
    pagos_mes = db.table("pagos").select("monto").eq("estatus", 1)\
        .gte("fecha_pago", str(primer_dia_mes)).execute()
    ingresos_mes_actual = sum(_safe_float(p["monto"]) for p in pagos_mes.data)

    pagos_mes_ant = db.table("pagos").select("monto").eq("estatus", 1)\
        .gte("fecha_pago", str(ultimo_mes_ini)).lte("fecha_pago", str(ultimo_mes_fin)).execute()
    ingresos_mes_anterior = sum(_safe_float(p["monto"]) for p in pagos_mes_ant.data)

    deuda_res = db.table("pagos").select("monto").eq("estatus", 0).execute()
    deuda_total = sum(_safe_float(p["monto"]) for p in deuda_res.data)

    # ── TORNEOS ────────────────────────────────────────────────
    torneos_activos = db.table("torneos").select("idtorneo", count="exact").eq("estatus", 1).execute()
    torneos_proximos = db.table("torneos").select("idtorneo", count="exact")\
        .gte("fecha", str(hoy)).execute()
    inscripciones_total = db.table("inscripciones_torneo").select("idinscripcion", count="exact").execute()

    torneos_lista_res = db.table("torneos").select("*")\
        .gte("fecha", str(hoy)).eq("estatus", 1).order("fecha").limit(5).execute()

    proximos_torneos_lista = []
    for t in torneos_lista_res.data:
        count_res = db.table("inscripciones_torneo").select("idinscripcion", count="exact")\
            .eq("idtorneo", t["idtorneo"]).execute()
        proximos_torneos_lista.append(TorneoProximo(
            idtorneo=t["idtorneo"],
            nombre=t["nombre"],
            fecha=str(t["fecha"]),
            sede=t["sede"],
            costo_inscripcion=_safe_float(t.get("costo_inscripcion")),
            total_inscritos=_safe_int(count_res.count),
        ))

    # ── ACTIVIDAD ──────────────────────────────────────────────
    nuevos_30d = db.table("alumnos").select("idalumno", count="exact")\
        .gte("fecharegistro", hace_30d).execute()
    movimientos_7d = db.table("pagos").select("idpago", count="exact")\
        .gte("fecharegistro", hace_7d).execute()

    # ── USUARIOS ───────────────────────────────────────────────
    query_usuarios = db.table("usuarios").select("idusuario, username, rol, fecha_creacion")

    ids_permitidos: list[int] = []
    if idescuela:
        owner_res = db.table("datosescuela").select("idusuario").eq("idescuela", idescuela).execute()
        profs_res = db.table("profesores").select("idusuario").eq("idescuela", idescuela).execute()
        if owner_res.data:
            ids_permitidos.append(owner_res.data[0]["idusuario"])
        ids_permitidos.extend([p["idusuario"] for p in profs_res.data if p.get("idusuario")])
        if ids_permitidos:
            query_usuarios = query_usuarios.in_("idusuario", ids_permitidos)

    usuarios_res = query_usuarios.execute()
    usuarios_data = usuarios_res.data or []

    conteo_roles: dict[str, int] = {}
    for u in usuarios_data:
        r = u.get("rol", "Desconocido")
        conteo_roles[r] = conteo_roles.get(r, 0) + 1

    # ── INGRESOS 6 MESES ───────────────────────────────────────
    pagos_6m = db.table("pagos").select("monto, fecha_pago")\
        .eq("estatus", 1).gte("fecha_pago", hace_6m).execute()

    meses_es = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
                7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}
    meses_map: dict = {}
    for p in pagos_6m.data:
        if p.get("fecha_pago"):
            d = datetime.fromisoformat(p["fecha_pago"][:10])
            key = f"{d.year}-{d.month:02d}"
            if key not in meses_map:
                meses_map[key] = {"mes_label": meses_es[d.month], "mes": key, "total": 0.0}
            meses_map[key]["total"] += _safe_float(p["monto"])

    ingresos_6_meses = [
        FinanceMes(mes_label=v["mes_label"], mes=v["mes"], total=round(v["total"], 2))
        for v in sorted(meses_map.values(), key=lambda x: x["mes"])
    ]

    # ── RESUMEN POR ESCUELA ────────────────────────────────────
    escuelas_resumen: list[EscuelaResumen] = []
    for esc in todas_escuelas:
        eid = esc["idescuela"]

        al_count = db.table("alumnos").select("idalumno", count="exact")\
            .eq("idescuela", eid).eq("estatus", 1).execute()
        pr_count = db.table("profesores").select("idprofesor", count="exact")\
            .eq("idescuela", eid).eq("estatus", 1).execute()

        pag_mes = db.table("pagos").select("monto").eq("idescuela", eid)\
            .eq("estatus", 1).gte("fecha_pago", str(primer_dia_mes)).execute()
        ing_mes = sum(_safe_float(p["monto"]) for p in pag_mes.data)

        deuda_esc = db.table("pagos").select("monto").eq("idescuela", eid).eq("estatus", 0).execute()
        deuda_e = sum(_safe_float(p["monto"]) for p in deuda_esc.data)

        pend_count = db.table("pagos").select("idpago", count="exact")\
            .eq("idescuela", eid).eq("estatus", 0).execute()

        escuelas_resumen.append(EscuelaResumen(
            idescuela=eid,
            nombreescuela=esc["nombreescuela"],
            logo_url=esc.get("logo_url"),
            color_paleta=esc.get("color_paleta"),
            alumnos_activos=_safe_int(al_count.count),
            profesores_activos=_safe_int(pr_count.count),
            ingresos_mes=round(ing_mes, 2),
            deuda_pendiente=round(deuda_e, 2),
            pagos_pendientes_count=_safe_int(pend_count.count),
        ))

    escuelas_resumen.sort(key=lambda x: x.ingresos_mes, reverse=True)

    return DashboardSuperAdmin(
        total_escuelas=len(todas_escuelas),
        total_usuarios=len(usuarios_data),
        total_alumnos_activos=_safe_int(alumnos_res.count),
        total_profesores_activos=_safe_int(profesores_res.count),
        ingresos_mes_actual=round(ingresos_mes_actual, 2),
        ingresos_mes_anterior=round(ingresos_mes_anterior, 2),
        deuda_total_pendiente=round(deuda_total, 2),
        torneos_activos=_safe_int(torneos_activos.count),
        torneos_proximos_count=_safe_int(torneos_proximos.count),
        total_inscripciones_torneo=_safe_int(inscripciones_total.count),
        alumnos_nuevos_30d=_safe_int(nuevos_30d.count),
        movimientos_financieros_7d=_safe_int(movimientos_7d.count),
        usuarios_por_rol=conteo_roles,
        ingresos_ultimos_6_meses=ingresos_6_meses,
        escuelas_resumen=escuelas_resumen,
        proximos_torneos=proximos_torneos_lista,
        usuarios_lista=[UsuarioItem(**u) for u in usuarios_data],
        escuelas=[EscuelaSimple(
            idescuela=e["idescuela"],
            nombreescuela=e["nombreescuela"],
            logo_url=e.get("logo_url")
        ) for e in todas_escuelas],
        filtro_aplicado=idescuela,
        resumen_sistema={"total_escuelas": len(todas_escuelas)},
        usuarios_online_recientes=0,
    )


# ─────────────────────────────────────────────────────────────
#  3. DASHBOARD PROFESOR
# ─────────────────────────────────────────────────────────────

@router.get("/profesor", response_model=DashboardProfesor)
async def get_professor_stats(
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    if user.get("rol") != "Profesor":
        raise HTTPException(status_code=403, detail="Acceso denegado. Se requiere rol Profesor.")

    id_usuario = user.get("idusuario")
    prof_res = db.table("profesores").select("idprofesor, idescuela")\
        .eq("idusuario", id_usuario).execute()
    if not prof_res.data:
        raise HTTPException(status_code=404, detail="Perfil de profesor no encontrado.")

    id_profesor = prof_res.data[0]["idprofesor"]
    id_escuela  = prof_res.data[0]["idescuela"]

    hoy       = date.today()
    hace_7d   = str(hoy - timedelta(days=6))
    hace_30d  = str(hoy - timedelta(days=30))

    # ── MIS ALUMNOS ────────────────────────────────────────────
    alumnos_activos_res = db.table("alumnos").select("idalumno", count="exact")\
        .eq("idprofesor", id_profesor).eq("estatus", 1).execute()
    alumnos_inactivos_res = db.table("alumnos").select("idalumno", count="exact")\
        .eq("idprofesor", id_profesor).eq("estatus", 0).execute()

    # IDs de mis alumnos activos
    mis_alumnos_res = db.table("alumnos")\
        .select("idalumno, nombres, apellidopaterno, fotoalumno, fechanacimiento, estatus, idgradoactual, grados:cintasgrados(idgrado, color, color_stripe, nivelkupdan, orden)")\
        .eq("idprofesor", id_profesor).eq("estatus", 1).execute()

    mis_ids = [a["idalumno"] for a in mis_alumnos_res.data]

    # ── DISTRIBUCIÓN CINTAS ────────────────────────────────────
    catalogo_cintas_prof = _get_cintas_escuela(id_escuela, db)
    distribucion_cintas = [
        BeltStat(**{k: v for k, v in c.items() if k in ("idgrado","color","color_stripe","nivelkupdan","count")})
        for c in _distribucion_cintas(mis_alumnos_res.data, catalogo_cintas_prof)
    ]

    # ── ASISTENCIA ─────────────────────────────────────────────
    asist_hoy = 0
    asist_semana: list[AsistenciaDia] = []

    if mis_ids:
        asist_hoy_res = db.table("asistencia").select("id", count="exact")\
            .eq("idescuela", id_escuela).eq("fecha", str(hoy))\
            .eq("presente", True).in_("idalumno", mis_ids).execute()
        asist_hoy = _safe_int(asist_hoy_res.count)

        asist_sem_res = db.table("asistencia").select("fecha")\
            .eq("idescuela", id_escuela).eq("presente", True)\
            .gte("fecha", hace_7d).in_("idalumno", mis_ids).execute()

        asistencia_map = {d["dia"]: {"label": d["label"], "dia": d["dia"], "presentes": 0}
                          for d in _dias_semana()}
        for a in asist_sem_res.data:
            dia_str = str(a["fecha"])
            if dia_str in asistencia_map:
                asistencia_map[dia_str]["presentes"] += 1

        asist_semana = [
            AsistenciaDia(fecha=v["dia"], label=v["label"], presentes=v["presentes"])
            for v in sorted(asistencia_map.values(), key=lambda x: x["dia"])
        ]
    else:
        asist_semana = [
            AsistenciaDia(fecha=d["dia"], label=d["label"], presentes=0)
            for d in _dias_semana()
        ]

    # ── PAGOS MIS ALUMNOS ──────────────────────────────────────
    pagos_pendientes_count = 0
    pagos_pendientes_monto = 0.0

    if mis_ids:
        pagos_pend = db.table("pagos").select("monto")\
            .eq("estatus", 0).in_("idalumno", mis_ids).execute()
        pagos_pendientes_count = len(pagos_pend.data)
        pagos_pendientes_monto = sum(_safe_float(p["monto"]) for p in pagos_pend.data)

    # ── PRÓXIMOS EXÁMENES ──────────────────────────────────────
    examenes_res = db.table("examenes").select("*")\
        .eq("idescuela", id_escuela).eq("estatus", 1)\
        .gte("fecha_programada", str(hoy)).order("fecha_programada").limit(3).execute()

    proximos_examenes = [
        ExamenProximo(
            idexamen=e["idexamen"],
            nombre_examen=e["nombre_examen"],
            fecha_programada=str(e["fecha_programada"]),
            lugar=e.get("lugar"),
            costo_examen=_safe_float(e.get("costo_examen")),
            sinodal=e.get("sinodal"),
        )
        for e in examenes_res.data
    ]

    # ── ALUMNOS EN TORNEO ──────────────────────────────────────
    torneo_count = 0
    if mis_ids:
        torneo_res = db.table("inscripciones_torneo")\
            .select("idinscripcion", count="exact").in_("idalumno", mis_ids).execute()
        torneo_count = _safe_int(torneo_res.count)

    # ── ALUMNOS AUSENTES +7 DÍAS ───────────────────────────────
    alumnos_ausentes: list[AlumnoAusente] = []
    if mis_ids:
        # Obtenemos la última asistencia de cada alumno
        for alumno in mis_alumnos_res.data:
            aid = alumno["idalumno"]
            ultima_res = db.table("asistencia").select("fecha")\
                .eq("idalumno", aid).eq("presente", True)\
                .order("fecha", desc=True).limit(1).execute()

            if ultima_res.data:
                ultima_fecha = datetime.strptime(str(ultima_res.data[0]["fecha"]), "%Y-%m-%d").date()
                dias_ausente = (hoy - ultima_fecha).days
                if dias_ausente >= 7:
                    alumnos_ausentes.append(AlumnoAusente(
                        idalumno=aid,
                        nombres=alumno["nombres"],
                        apellidopaterno=alumno["apellidopaterno"],
                        fotoalumno=alumno.get("fotoalumno"),
                        ultima_asistencia=str(ultima_fecha),
                        dias_ausente=dias_ausente,
                    ))
            else:
                alumnos_ausentes.append(AlumnoAusente(
                    idalumno=aid,
                    nombres=alumno["nombres"],
                    apellidopaterno=alumno["apellidopaterno"],
                    fotoalumno=alumno.get("fotoalumno"),
                    ultima_asistencia=None,
                    dias_ausente=None,
                ))

    alumnos_ausentes.sort(key=lambda x: (x.dias_ausente is None, -(x.dias_ausente or 0)))

    # ── CUMPLEAÑOS PRÓXIMOS ────────────────────────────────────
    cumpleanos: list[AlumnoCumple] = []
    for a in mis_alumnos_res.data:
        if not a.get("fechanacimiento"):
            continue
        try:
            fn = datetime.strptime(str(a["fechanacimiento"]), "%Y-%m-%d")
            cumple = fn.replace(year=hoy.year).date()
            if hoy <= cumple <= hoy + timedelta(days=7):
                cumpleanos.append(AlumnoCumple(
                    idalumno=a["idalumno"],
                    nombres=a["nombres"],
                    apellidopaterno=a["apellidopaterno"],
                    fechanacimiento=str(a["fechanacimiento"]),
                    edad=hoy.year - fn.year,
                    fecha_display=fn.strftime("%d/%m"),
                ))
        except ValueError:
            continue

    # ── ÚLTIMAS PROMOCIONES ────────────────────────────────────
    ultimas_promociones: list[PromocionGrado] = []
    if mis_ids:
        historial_res = db.table("historial_grados")\
            .select("idhistorial, idalumno, fecha_examen, idgrado_anterior, idgrado_nuevo, grado_ant:cintasgrados!historial_grados_idgrado_anterior_fkey(color), grado_nvo:cintasgrados!historial_grados_idgrado_nuevo_fkey(color, nivelkupdan)")\
            .in_("idalumno", mis_ids)\
            .order("fecha_examen", desc=True).limit(5).execute()

        alumnos_dict = {a["idalumno"]: a for a in mis_alumnos_res.data}
        for h in historial_res.data:
            al = alumnos_dict.get(h["idalumno"], {})
            g_ant = h.get("grado_ant") or {}
            g_nvo = h.get("grado_nvo") or {}
            ultimas_promociones.append(PromocionGrado(
                idhistorial=h["idhistorial"],
                nombres=al.get("nombres", ""),
                apellidopaterno=al.get("apellidopaterno", ""),
                grado_anterior=g_ant.get("color", ""),
                grado_nuevo=g_nvo.get("color", ""),
                nivelkupdan=g_nvo.get("nivelkupdan", ""),
                fecha_examen=str(h["fecha_examen"]),
            ))

    # ── LISTA COMPLETA MIS ALUMNOS ─────────────────────────────
    mis_alumnos_lista: list[AlumnoLista] = []
    for a in sorted(mis_alumnos_res.data, key=lambda x: x["apellidopaterno"]):
        aid = a["idalumno"]
        g = a.get("grados") or {}

        # última asistencia
        ult_asist_res = db.table("asistencia").select("fecha")\
            .eq("idalumno", aid).eq("presente", True)\
            .order("fecha", desc=True).limit(1).execute()
        ultima_asistencia = str(ult_asist_res.data[0]["fecha"]) if ult_asist_res.data else None

        # pagos pendientes
        pend_al = db.table("pagos").select("idpago", count="exact")\
            .eq("idalumno", aid).eq("estatus", 0).execute()

        mis_alumnos_lista.append(AlumnoLista(
            idalumno=aid,
            nombres=a["nombres"],
            apellidopaterno=a["apellidopaterno"],
            fotoalumno=a.get("fotoalumno"),
            fechanacimiento=str(a["fechanacimiento"]) if a.get("fechanacimiento") else None,
            cinta_color=g.get("color", "Blanca"),
            cinta_nivel=g.get("nivelkupdan", ""),
            ultima_asistencia=ultima_asistencia,
            pagos_pendientes=_safe_int(pend_al.count),
        ))

    total_activos = _safe_int(alumnos_activos_res.count)

    return DashboardProfesor(
        mis_alumnos_activos=total_activos,
        mis_alumnos_inactivos=_safe_int(alumnos_inactivos_res.count),
        mis_asistencias_hoy=asist_hoy,
        asistencia_semana=asist_semana,
        distribucion_cintas=distribucion_cintas,
        mis_pagos_pendientes_count=pagos_pendientes_count,
        mis_pagos_pendientes_monto=round(pagos_pendientes_monto, 2),
        proximos_examenes=proximos_examenes,
        mis_alumnos_torneo_count=torneo_count,
        alumnos_ausentes=alumnos_ausentes[:8],
        cumpleanos_proximos=cumpleanos,
        ultimas_promociones=ultimas_promociones,
        mis_alumnos_lista=mis_alumnos_lista,
        # Compatibilidad hacia atrás
        total_alumnos=total_activos,
        distribucion_cintas_porcentaje={v.color: round((v.count / total_activos) * 100, 2) for v in distribucion_cintas} if total_activos > 0 else {},
        mensualidades_stats={"pagadas": 0, "pendientes": pagos_pendientes_count},
        alumnos_en_torneo=torneo_count,
        asistencia_reciente=[],
    )