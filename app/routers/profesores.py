from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from typing import List
from supabase import Client
import uuid

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.profesores import Profesor, ProfesorCreate, ProfesorUpdate
from app.schemas.usuarios import UserRole

router = APIRouter(prefix="/profesores", tags=["Gestión de Profesores"])

@router.get("/mi-perfil", response_model=Profesor)
async def obtener_perfil_propio_profesor(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Permite al profesor logueado obtener su propia información de perfil.
    """
    id_usuario = current_user.get("idusuario")
    result = db.table("profesores").select("*").eq("idusuario", id_usuario).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Perfil de profesor no encontrado.")
    
    return result.data[0]

@router.put("/mi-perfil", response_model=Profesor)
async def actualizar_mi_perfil(
    datos: ProfesorUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Permite al profesor logueado actualizar sus propios datos personales.
    """
    if current_user.get("rol") != UserRole.PROFESOR:
        raise HTTPException(status_code=403, detail="Acceso denegado.")

    id_usuario = current_user.get("idusuario")
    
    # Limpiamos datos nulos para la actualización
    update_data = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No se enviaron datos para actualizar.")

    try:
        result = db.table("profesores").update(update_data).eq("idusuario", id_usuario).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="No se pudo encontrar el perfil para actualizar.")
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al actualizar perfil: {str(e)}")

@router.post("/upload-foto", response_model=Profesor)
async def subir_foto_profesor(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    El profesor logueado sube su propia foto de perfil.
    """
    if current_user.get("rol") != UserRole.PROFESOR:
        raise HTTPException(status_code=403, detail="Solo los profesores pueden subir su propia foto.")

    id_usuario = current_user.get("idusuario")
    
    # 1. Obtener el ID del profesor
    profe_res = db.table("profesores").select("idprofesor").eq("idusuario", id_usuario).execute()
    if not profe_res.data:
        raise HTTPException(status_code=404, detail="Perfil de profesor no encontrado.")
    
    id_profesor = profe_res.data[0]["idprofesor"]

    # 2. Validar archivo
    extension = file.filename.split(".")[-1].lower()
    if extension not in ["jpg", "jpeg", "png"]:
        raise HTTPException(status_code=400, detail="Formato no permitido. Usa JPG o PNG.")

    # 3. Subir a Storage
    file_path = f"perfiles/profesor_{id_profesor}_{uuid.uuid4()}.{extension}"
    file_content = await file.read()

    try:
        # Nota: Se usa el bucket 'alumnos' que ya tiene las políticas configuradas
        db.storage.from_("alumnos").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": file.content_type}
        )

        foto_url = db.storage.from_("alumnos").get_public_url(file_path)

        # 4. Actualizar tabla profesores
        update_res = db.table("profesores").update({"foto_url": foto_url}).eq("idprofesor", id_profesor).execute()
        
        return update_res.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir la foto del profesor: {str(e)}")

@router.get("/", response_model=List[Profesor])
def listar_profesores(db: Client = Depends(get_db)):
    """
    Lista todos los profesores registrados (útil para administradores y escuelas).
    """
    result = db.table("profesores").select("*").execute()
    return result.data

@router.get("/{idprofesor}", response_model=Profesor)
def obtener_profesor(idprofesor: int, db: Client = Depends(get_db)):
    """
    Obtiene la información pública de un profesor específico por su ID.
    """
    result = db.table("profesores").select("*").eq("idprofesor", idprofesor).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Profesor no encontrado")
    return result.data[0]