from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from supabase import Client
import uuid

from utils.database import get_db
from utils.auth_utils import get_current_user
from schemas.catalogos import Escuela, EscuelaBase
from schemas.usuarios import UserRole

router = APIRouter(prefix="/escuelas", tags=["Gestión de la Escuela"])

@router.get("/mi-escuela", response_model=Escuela)
async def obtener_datos_escuela(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Obtiene los datos de la escuela vinculada al usuario actual (Escuela o Profesor).
    """
    id_usuario = current_user.get("idusuario")
    rol = current_user.get("rol")

    # Si es Escuela, buscamos por su idusuario
    if rol == UserRole.ESCUELA:
        result = db.table("datosescuela").select("*").eq("idusuario", id_usuario).execute()
    # Si es Profesor, buscamos la escuela a la que pertenece
    elif rol == UserRole.PROFESOR:
        profe_res = db.table("profesores").select("idescuela").eq("idusuario", id_usuario).execute()
        if not profe_res.data:
            raise HTTPException(status_code=404, detail="Perfil de profesor no encontrado.")
        
        id_escuela = profe_res.data[0]["idescuela"]
        result = db.table("datosescuela").select("*").eq("idescuela", id_escuela).execute()
    else:
        raise HTTPException(status_code=403, detail="No tienes permisos para ver datos de escuela.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Datos de escuela no encontrados.")
    
    return result.data[0]

@router.post("/upload-logo", response_model=Escuela)
async def subir_logo_escuela(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Permite al director de la escuela subir su logotipo.
    """
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(status_code=403, detail="Solo el administrador de la escuela puede subir el logo.")

    id_usuario = current_user.get("idusuario")
    
    # 1. Obtener el registro de la escuela
    escuela_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
    if not escuela_res.data:
        raise HTTPException(status_code=404, detail="Perfil de escuela no encontrado.")
    
    id_escuela = escuela_res.data[0]["idescuela"]

    # 2. Validar archivo
    extension = file.filename.split(".")[-1].lower()
    if extension not in ["jpg", "jpeg", "png"]:
        raise HTTPException(status_code=400, detail="Formato no permitido. Usa JPG o PNG.")

    # 3. Subir a Storage
    # Usamos el bucket 'alumnos' que ya tiene las políticas RLS abiertas o gestionadas por Service Role
    file_path = f"logos/escuela_{id_escuela}_{uuid.uuid4()}.{extension}"
    file_content = await file.read()

    try:
        db.storage.from_("alumnos").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": file.content_type}
        )

        logo_url = db.storage.from_("alumnos").get_public_url(file_path)

        # 4. Actualizar tabla datosescuela
        update_res = db.table("datosescuela").update({"logo_url": logo_url}).eq("idescuela", id_escuela).execute()
        
        return update_res.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir el logotipo: {str(e)}")