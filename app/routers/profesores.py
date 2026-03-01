from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from typing import List
from supabase import Client
import uuid

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.profesores import Profesor, ProfesorCreate, ProfesorUpdate
from app.schemas.roles import UserRole

# Se elimina el prefix="/profesores" para evitar la duplicidad con el prefijo definido en main.py
router = APIRouter(tags=["Gestión de Profesores"])

@router.get("/", response_model=List[Profesor])
async def listar_profesores_escuela(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Lista los profesores pertenecientes a la escuela del usuario logueado.
    URL Final: /profesores/
    """
    id_usuario = current_user.get("idusuario")
    rol = current_user.get("rol")

    if rol != UserRole.ESCUELA:
        raise HTTPException(status_code=403, detail="Solo las escuelas pueden listar sus profesores.")

    # 1. Obtener idescuela desde la tabla datosescuela
    escuela_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
    if not escuela_res.data:
        raise HTTPException(status_code=404, detail="Perfil de escuela no encontrado.")
    
    id_escuela = escuela_res.data[0]["idescuela"]

    # 2. Filtrar profesores por esa escuela
    result = db.table("profesores").select("*").eq("idescuela", id_escuela).execute()
    return result.data

@router.put("/{idprofesor}", response_model=Profesor)
async def actualizar_profesor_escuela(
    idprofesor: int,
    datos: ProfesorUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Permite a la escuela actualizar los datos de uno de sus profesores.
    """
    id_usuario_escuela = current_user.get("idusuario")
    
    # 1. Validar que el profesor pertenezca a la escuela del solicitante
    escuela_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario_escuela).execute()
    if not escuela_res.data:
         raise HTTPException(status_code=404, detail="Perfil de escuela no encontrado.")
         
    id_escuela = escuela_res.data[0]["idescuela"]

    profe_check = db.table("profesores").select("idescuela").eq("idprofesor", idprofesor).execute()
    if not profe_check.data or profe_check.data[0]["idescuela"] != id_escuela:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este profesor.")

    # 2. Actualizar datos filtrando nulos
    update_data = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar.")

    try:
        result = db.table("profesores").update(update_data).eq("idprofesor", idprofesor).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{idprofesor}/upload-foto", response_model=Profesor)
async def subir_foto_profesor_por_escuela(
    idprofesor: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Permite a la escuela subir o actualizar la foto de uno de sus profesores mediante su ID.
    """
    id_usuario_escuela = current_user.get("idusuario")
    rol = current_user.get("rol")

    if rol != UserRole.ESCUELA:
        raise HTTPException(status_code=403, detail="Solo las escuelas pueden subir fotos de sus profesores.")

    # 1. Validar que el profesor pertenece a la escuela
    esc_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario_escuela).execute()
    id_escuela = esc_res.data[0]["idescuela"]

    profe_check = db.table("profesores").select("idescuela").eq("idprofesor", idprofesor).execute()
    if not profe_check.data or profe_check.data[0]["idescuela"] != id_escuela:
        raise HTTPException(status_code=403, detail="El profesor no pertenece a tu escuela.")

    # 2. Validar archivo
    extension = file.filename.split(".")[-1].lower()
    if extension not in ["jpg", "jpeg", "png"]:
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes JPG o PNG.")

    # 3. Preparar subida
    file_path = f"perfiles/profesor_{idprofesor}_{uuid.uuid4().hex[:8]}.{extension}"
    file_content = await file.read()

    try:
        # Subida al bucket 'alumnos'
        db.storage.from_("alumnos").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": file.content_type}
        )
        foto_url = db.storage.from_("alumnos").get_public_url(file_path)

        # 4. Actualizar tabla
        update_res = db.table("profesores").update({"foto_url": foto_url}).eq("idprofesor", idprofesor).execute()
        return update_res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir la foto: {str(e)}")

@router.get("/mi-perfil", response_model=Profesor)
async def obtener_perfil_propio_profesor(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Permite al profesor ver sus propios datos.
    """
    if current_user.get("rol") != UserRole.PROFESOR:
        raise HTTPException(status_code=403, detail="Ruta exclusiva para profesores.")
    
    id_usuario = current_user.get("idusuario")
    result = db.table("profesores").select("*").eq("idusuario", id_usuario).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    return result.data[0]

@router.post("/upload-foto", response_model=Profesor)
async def subir_foto_profesor_propia(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    El profesor logueado sube su propia foto de perfil.
    """
    if current_user.get("rol") != UserRole.PROFESOR:
        raise HTTPException(status_code=403, detail="Acción exclusiva para profesores.")

    id_usuario = current_user.get("idusuario")
    profe_res = db.table("profesores").select("idprofesor").eq("idusuario", id_usuario).execute()
    if not profe_res.data:
        raise HTTPException(status_code=404, detail="Perfil de profesor no encontrado.")
        
    id_profesor = profe_res.data[0]["idprofesor"]

    extension = file.filename.split(".")[-1].lower()
    if extension not in ["jpg", "jpeg", "png"]:
        raise HTTPException(status_code=400, detail="Formato de imagen inválido.")

    file_path = f"perfiles/profesor_{id_profesor}_{uuid.uuid4().hex[:8]}.{extension}"
    file_content = await file.read()

    try:
        # Subida al bucket 'alumnos' (compartido para imágenes de perfil)
        db.storage.from_("alumnos").upload(
            path=file_path, 
            file=file_content, 
            file_options={"content-type": file.content_type}
        )
        foto_url = db.storage.from_("alumnos").get_public_url(file_path)

        update_res = db.table("profesores").update({"foto_url": foto_url}).eq("idprofesor", id_profesor).execute()
        return update_res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el servidor de archivos: {str(e)}")