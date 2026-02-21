from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from supabase import Client
import uuid

from utils.database import get_db
from utils.auth_utils import get_current_user
from schemas.escuela import Escuela, EscuelaBase, EscuelaUpdate
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
@router.put("/mi-escuela", response_model=Escuela)
async def actualizar_perfil_escuela(
    datos: EscuelaUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Actualiza la información de la escuela, incluyendo dirección, lema,
    teléfono, paleta de colores y el nuevo campo de correo_escuela.
    """
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(status_code=403, detail="Solo el administrador de la escuela puede editar el perfil.")

    id_usuario = current_user.get("idusuario")
    
    # Extraemos solo los campos que el usuario envió realmente
    update_data = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No se enviaron datos para actualizar.")

    try:
        # Actualizamos en Supabase filtrando por el dueño (idusuario)
        result = db.table("datosescuela").update(update_data).eq("idusuario", id_usuario).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="No se pudo encontrar el registro de la escuela.")
            
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno al actualizar perfil: {str(e)}")

@router.post("/upload-logo", response_model=Escuela)
async def subir_logo_escuela(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Sube un nuevo logotipo al bucket de alumnos y actualiza la URL en el perfil.
    """
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(status_code=403, detail="Permisos insuficientes para subir archivos.")

    id_usuario = current_user.get("idusuario")
    escuela_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
    
    if not escuela_res.data:
        raise HTTPException(status_code=404, detail="Escuela no encontrada para este usuario.")
    
    id_escuela = escuela_res.data[0]["idescuela"]
    
    # Generamos un nombre de archivo único
    extension = file.filename.split(".")[-1].lower()
    file_path = f"logos/escuela_{id_escuela}_{uuid.uuid4()}.{extension}"
    file_content = await file.read()

    try:
        # Subida al Storage
        db.storage.from_("alumnos").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": file.content_type}
        )
        
        # Generar URL y guardar en tabla
        logo_url = db.storage.from_("alumnos").get_public_url(file_path)
        update_res = db.table("datosescuela").update({"logo_url": logo_url}).eq("idescuela", id_escuela).execute()
        
        return update_res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar la imagen: {str(e)}")