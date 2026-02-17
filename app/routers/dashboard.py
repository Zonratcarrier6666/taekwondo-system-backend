from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client
from datetime import datetime, timedelta
from typing import Optional
from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.dashboard import DashboardStats, BeltStat, FinanceStat

router = APIRouter(prefix="/dashboard", tags=["Estadísticas y Dashboard"])

# --- DASHBOARD ESCUELA ---
@router.get("/escuela", response_model=DashboardStats)
async def get_school_stats(
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    id_usuario = user.get("idusuario")
    rol = user.get("rol")
    
    id_escuela = None
    if rol == "Escuela":
        res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if res.data: id_escuela = res.data[0]["idescuela"]
    elif rol == "Profesor":
        res = db.table("profesores").select("idescuela").eq("idusuario", id_usuario).execute()
        if res.data: id_escuela = res.data[0]["idescuela"]

    if not id_escuela:
        raise HTTPException(status_code=403, detail="No tienes una escuela asignada en tu perfil.")

    alumnos_res = db.table("alumnos").select("idalumno", count="exact").eq("idescuela", id_escuela).execute()
    total_alumnos = alumnos_res.count if alumnos_res.count else 0

    cintas_res = db.table("alumnos").select("idgradoactual, grados:cintasgrados(color)").eq("idescuela", id_escuela).execute()
    conteo_cintas = {}
    for a in cintas_res.data:
        if a.get("grados"):
            color = a["grados"]["color"]
            conteo_cintas[color] = conteo_cintas.get(color, 0) + 1
    dist_cintas = [BeltStat(color=k, count=v) for k, v in conteo_cintas.items()]

    una_semana_atras = (datetime.now() - timedelta(days=7)).date().isoformat()
    pagos_res = db.table("pagos").select("monto, fecha_pago")\
        .eq("idescuela", id_escuela)\
        .eq("estatus", 1)\
        .gte("fecha_pago", una_semana_atras).execute()
    
    total_semana = sum(float(p["monto"]) for p in pagos_res.data)
    finanzas_dia = {}
    for p in pagos_res.data:
        if p["fecha_pago"]:
            dia = datetime.fromisoformat(p["fecha_pago"].split('T')[0]).strftime("%a")
            finanzas_dia[dia] = finanzas_dia.get(dia, 0) + float(p["monto"])
    finanzas_lista = [FinanceStat(dia=k, monto=v) for k, v in finanzas_dia.items()]

    pendientes_res = db.table("pagos").select("idpago", count="exact").eq("idescuela", id_escuela).eq("estatus", 0).execute()
    torneos_res = db.table("inscripciones_torneo").select("idinscripcion, alumnos!inner(idescuela)", count="exact")\
        .eq("alumnos.idescuela", id_escuela).execute()

    return DashboardStats(
        total_alumnos=total_alumnos,
        ingresos_semanales=total_semana,
        pagos_pendientes_count=pendientes_res.count or 0,
        alumnos_torneo_count=torneos_res.count or 0,
        distribucion_cintas=dist_cintas,
        finanzas_semana=finanzas_lista,
        proximos_torneos=[]
    )

# --- DASHBOARD SUPER ADMIN ---
@router.get("/superadmin")
async def get_superadmin_stats(
    idescuela: Optional[int] = Query(None, description="Filtrar estadísticas y usuarios por una escuela específica"),
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    if user.get("rol") != "SuperAdmin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Se requiere rol SuperAdmin.")

    # 1. Lista de todas las escuelas (siempre necesaria para el selector del frontend)
    escuelas_res = db.table("datosescuela").select("idescuela, nombreescuela, logo_url").execute()
    
    # 2. Lógica de filtrado de usuarios
    query_usuarios = db.table("usuarios").select("idusuario, username, rol, fecha_creacion").neq("rol", "SuperAdmin")
    
    if idescuela:
        # Para filtrar usuarios por escuela, necesitamos identificar quiénes pertenecen a ella
        # Obtenemos el dueño (Escuela) y los profesores vinculados
        owner_res = db.table("datosescuela").select("idusuario").eq("idescuela", idescuela).execute()
        profs_res = db.table("profesores").select("idusuario").eq("idescuela", idescuela).execute()
        
        ids_permitidos = []
        if owner_res.data: ids_permitidos.append(owner_res.data[0]["idusuario"])
        ids_permitidos.extend([p["idusuario"] for p in profs_res.data])
        
        # Filtramos la lista de usuarios final
        query_usuarios = query_usuarios.in_("idusuario", ids_permitidos)

    usuarios_res = query_usuarios.execute()
    
    conteo_roles = {}
    for u in usuarios_res.data:
        r = u["rol"]
        conteo_roles[r] = conteo_roles.get(r, 0) + 1

    # 3. Usuarios creados recientemente (actividad última hora)
    hace_una_hora = (datetime.now() - timedelta(hours=1)).isoformat()
    query_recientes = db.table("usuarios").select("idusuario", count="exact").gte("fecha_creacion", hace_una_hora)
    
    if idescuela:
        # Aplicamos el mismo filtro de IDs si hay escuela seleccionada
        query_recientes = query_recientes.in_("idusuario", ids_permitidos)
        
    recientes_res = query_recientes.execute()

    return {
        "total_usuarios": len(usuarios_res.data),
        "usuarios_online_recientes": recientes_res.count or 0,
        "usuarios_por_rol": conteo_roles,
        "usuarios_lista": usuarios_res.data,
        "escuelas": escuelas_res.data,
        "filtro_aplicado": idescuela,
        "resumen_sistema": {
            "total_escuelas": len(escuelas_res.data)
        }
    }

# --- DASHBOARD PROFESOR ---
@router.get("/profesor")
async def get_professor_stats(
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    id_usuario = user.get("idusuario")
    if user.get("rol") != "Profesor":
        raise HTTPException(status_code=403, detail="Acceso denegado. Se requiere rol Profesor.")

    # Obtener el ID del profesor
    prof_res = db.table("profesores").select("idprofesor, idescuela").eq("idusuario", id_usuario).execute()
    if not prof_res.data:
        raise HTTPException(status_code=404, detail="Perfil de profesor no encontrado.")
    
    id_profesor = prof_res.data[0]["idprofesor"]
    id_escuela = prof_res.data[0]["idescuela"]

    # 1. Alumnos con sus cintas (Distribución porcentual de sus propios alumnos)
    alumnos_profe = db.table("alumnos").select("idgradoactual, grados:cintasgrados(color)").eq("idprofesor", id_profesor).execute()
    total_profe = len(alumnos_profe.data)
    conteo_cintas = {}
    for a in alumnos_profe.data:
        if a.get("grados"):
            color = a["grados"]["color"]
            conteo_cintas[color] = conteo_cintas.get(color, 0) + 1
    
    dist_porcentaje = {k: round((v / total_profe) * 100, 2) for k, v in conteo_cintas.items()} if total_profe > 0 else {}

    # 2. Asistencia (Promedio de asistencia de la semana para sus alumnos)
    una_semana_atras = (datetime.now() - timedelta(days=7)).date().isoformat()
    asistencia_res = db.table("asistencia").select("presente")\
        .eq("idescuela", id_escuela)\
        .gte("fecha", una_semana_atras)\
        .in_("idalumno", [a["idgradoactual"] for a in alumnos_profe.data if "idalumno" in a])\
        .execute()

    # 3. Torneos (Alumnos del profesor inscritos en torneos activos)
    inscripciones_res = db.table("inscripciones_torneo")\
        .select("idinscripcion, torneos(nombre), alumnos!inner(idprofesor)")\
        .eq("alumnos.idprofesor", id_profesor).execute()

    # 4. Pagos por mensualidad (Pagados vs No Pagados de sus alumnos)
    pagos_res = db.table("pagos")\
        .select("estatus, id_tipo_pago, idalumno")\
        .eq("id_tipo_pago", 1) \
        .in_("idalumno", [a["idalumno"] for a in alumnos_profe.data if "idalumno" in a])\
        .execute()
    
    mensualidades_pagadas = len([p for p in pagos_res.data if p["estatus"] == 1])
    mensualidades_pendientes = len([p for p in pagos_res.data if p["estatus"] == 0])

    return {
        "total_alumnos": total_profe,
        "distribucion_cintas_porcentaje": dist_porcentaje,
        "mensualidades_stats": {
            "pagadas": mensualidades_pagadas,
            "pendientes": mensualidades_pendientes
        },
        "alumnos_en_torneo": len(inscripciones_res.data),
        "asistencia_reciente": asistencia_res.data if asistencia_res.data else []
    }