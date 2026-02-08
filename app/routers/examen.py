from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from supabase import Client
import os

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.examen import Examen, ExamenCreate, CargaResultadosMasivos
from app.schemas.usuarios import UserRole

# Se mantiene el prefix pero recuerda que en main.py ya hay uno. 
# Si en main.py tienes prefix="/examenes", la ruta queda /examenes/examenes/
router = APIRouter(tags=["Gestión de Exámenes"])

@router.post("/", response_model=Examen, status_code=status.HTTP_201_CREATED)
async def crear_examen(
    datos: ExamenCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Crea un nuevo evento de examen. 
    Usa mode='json' para evitar errores de serialización de fechas.
    """
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")

    if rol not in [UserRole.ESCUELA, UserRole.PROFESOR, UserRole.SUPERADMIN]:
        raise HTTPException(status_code=403, detail="No tienes permisos para crear exámenes.")

    id_escuela = None
    if rol == UserRole.ESCUELA:
        res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if res.data: id_escuela = res.data[0]["idescuela"]
    elif rol == UserRole.PROFESOR:
        res = db.table("profesores").select("idescuela").eq("idusuario", id_usuario).execute()
        if res.data: id_escuela = res.data[0]["idescuela"]

    if not id_escuela:
        raise HTTPException(status_code=404, detail="No se encontró una escuela vinculada a tu perfil.")
    
    # FIX: Usar mode='json' convierte objetos date/datetime a strings
    payload = datos.model_dump(mode='json')
    payload["idescuela"] = id_escuela

    try:
        result = db.table("examenes").insert(payload).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al crear: {str(e)}")

@router.post("/{idexamen}/registrar-resultados-masivos")
async def registrar_resultados_masivos(
    idexamen: int,
    datos: CargaResultadosMasivos,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Procesa múltiples promociones vinculadas a un examen.
    """
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")
    
    id_evaluador = None
    if rol == UserRole.PROFESOR:
        profe_res = db.table("profesores").select("idprofesor").eq("idusuario", id_usuario).execute()
        if profe_res.data:
            id_evaluador = profe_res.data[0]["idprofesor"]

    exitos = 0
    errores = []
    fecha_str = str(datos.fecha_examen)

    for item in datos.resultados:
        try:
            alumno = db.table("alumnos").select("idgradoactual").eq("idalumno", item.idalumno).execute()
            if not alumno.data:
                errores.append(f"Alumno {item.idalumno} no encontrado")
                continue
            
            grado_anterior = alumno.data[0]["idgradoactual"]

            db.table("historial_grados").insert({
                "idalumno": item.idalumno,
                "idgrado_anterior": grado_anterior,
                "idgrado_nuevo": item.id_nuevo_grado,
                "idexamen": idexamen,
                "fecha_examen": fecha_str,
                "idprofesor_evaluador": id_evaluador,
                "notas": item.notas
            }).execute()

            db.table("alumnos").update({"idgradoactual": item.id_nuevo_grado}).eq("idalumno", item.idalumno).execute()
            exitos += 1
        except Exception as e:
            errores.append(f"Error con alumno {item.idalumno}: {str(e)}")

    return {
        "status": "proceso_completado",
        "procesados_exitosamente": exitos,
        "errores": errores
    }

@router.get("/", response_model=List[Examen])
async def listar_examenes(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    id_usuario = current_user.get("idusuario")
    rol = current_user.get("rol")
    
    id_escuela = None
    if rol == UserRole.ESCUELA:
        perfil = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
    else:
        perfil = db.table("profesores").select("idescuela").eq("idusuario", id_usuario).execute()

    if not perfil.data:
        raise HTTPException(status_code=404, detail="Escuela no identificada.")

    id_escuela = perfil.data[0]["idescuela"]
    result = db.table("examenes").select("*").eq("idescuela", id_escuela).order("fecha_programada", desc=True).execute()
    return result.data