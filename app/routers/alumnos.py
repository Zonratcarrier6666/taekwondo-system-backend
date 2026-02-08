from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from typing import List
from supabase import Client
import uuid
import os

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.alumnos import Alumno, AlumnoCreate, AlumnoUpdate
from app.schemas.usuarios import UserRole

router = APIRouter()

@router.post("/", response_model=Alumno, status_code=status.HTTP_201_CREATED)
async def registrar_alumno_predictivo(
    alumno: AlumnoCreate, 
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")
    
    if rol not in [UserRole.ESCUELA, UserRole.PROFESOR]:
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar alumnos.")

    id_escuela = None
    id_profesor = None

    if rol == UserRole.PROFESOR:
        profe_data = db.table("profesores").select("idprofesor, idescuela").eq("idusuario", id_usuario).execute()
        if not profe_data.data:
            raise HTTPException(status_code=404, detail="Perfil de profesor no encontrado.")
        id_profesor = profe_data.data[0]["idprofesor"]
        id_escuela = profe_data.data[0]["idescuela"]
        
    elif rol == UserRole.ESCUELA:
        escuela_data = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if not escuela_data.data:
            raise HTTPException(status_code=404, detail="Perfil de escuela no encontrado.")
        id_escuela = escuela_data.data[0]["idescuela"]
        id_profesor = alumno.idprofesor

    data_final = alumno.model_dump(mode='json')
    data_final["idescuela"] = id_escuela
    data_final["idprofesor"] = id_profesor

    try:
        result = db.table("alumnos").insert(data_final).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al procesar registro: {str(e)}")

@router.get("/", response_model=List[Alumno])
async def listar_alumnos_con_filtro(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")
    query = db.table("alumnos").select("*")
    
    if rol == UserRole.SUPERADMIN:
        pass 
    elif rol == UserRole.ESCUELA:
        escuela = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if escuela.data:
            query = query.eq("idescuela", escuela.data[0]["idescuela"])
    elif rol == UserRole.PROFESOR:
        profe = db.table("profesores").select("idprofesor").eq("idusuario", id_usuario).execute()
        if profe.data:
            query = query.eq("idprofesor", profe.data[0]["idprofesor"])
            
    result = query.execute()
    return result.data

@router.get("/{idalumno}", response_model=Alumno)
async def obtener_detalle_alumno(
    idalumno: int,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")

    result = db.table("alumnos").select("*").eq("idalumno", idalumno).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Alumno no encontrado.")
    
    alumno = result.data[0]

    if rol != UserRole.SUPERADMIN:
        if rol == UserRole.ESCUELA:
            escuela = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
            if not escuela.data or escuela.data[0]["idescuela"] != alumno["idescuela"]:
                raise HTTPException(status_code=403, detail="No tienes permiso para ver este alumno.")
        elif rol == UserRole.PROFESOR:
            profe = db.table("profesores").select("idprofesor").eq("idusuario", id_usuario).execute()
            if not profe.data or profe.data[0]["idprofesor"] != alumno["idprofesor"]:
                raise HTTPException(status_code=403, detail="Este alumno no está asignado a tu perfil.")

    return alumno

@router.post("/{idalumno}/upload-foto", response_model=Alumno)
async def subir_foto_archivo(
    idalumno: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Sube un archivo al Storage de Supabase.
    """
    # 1. Verificar permisos
    alumno_db = await obtener_detalle_alumno(idalumno, current_user, db)

    # 2. Validar extensión
    extension = file.filename.split(".")[-1].lower()
    if extension not in ["jpg", "jpeg", "png"]:
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes JPG o PNG.")

    # 3. Preparar archivo y ruta única
    file_path = f"{idalumno}_{uuid.uuid4()}.{extension}"
    file_content = await file.read()

    try:
        # Intentar subir al bucket 'alumnos'
        # Usamos try/except específico para capturar la respuesta de Supabase
        storage_res = db.storage.from_("alumnos").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": file.content_type}
        )

        # Obtener URL pública
        foto_url = db.storage.from_("alumnos").get_public_url(file_path)

        # 4. Actualizar la base de datos
        update_res = db.table("alumnos").update({"fotoalumno": foto_url}).eq("idalumno", idalumno).execute()
        return update_res.data[0]

    except Exception as e:
        error_msg = str(e)
        print(f"CRITICAL STORAGE ERROR: {error_msg}")
        
        if "row-level security" in error_msg.lower() or "403" in error_msg:
             raise HTTPException(
                status_code=500, 
                detail=f"RLS sigue bloqueando. Ejecuta el SQL de 'Control Total' en Supabase. Error: {error_msg}"
            )
            
        raise HTTPException(status_code=500, detail=f"Error inesperado en Storage: {error_msg}")

@router.put("/{idalumno}", response_model=Alumno)
async def actualizar_alumno(
    idalumno: int,
    datos: AlumnoUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    await obtener_detalle_alumno(idalumno, current_user, db)
    update_dict = datos.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar.")
    try:
        result = db.table("alumnos").update(update_dict).eq("idalumno", idalumno).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al actualizar: {str(e)}")