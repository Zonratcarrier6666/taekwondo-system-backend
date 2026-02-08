from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client
from typing import List

from app.utils.database import get_db
from app.utils.security import get_password_hash
from app.utils.auth_utils import get_current_user
from app.schemas.usuarios import (
    Usuario, UserRole, RegistroEscuelaCompleto, RegistroProfesorCompleto
)

router = APIRouter(prefix="/usuarios", tags=["Gestión de Usuarios"])

@router.post("/registrar-escuela", response_model=Usuario, status_code=status.HTTP_201_CREATED)
async def registrar_escuela(
    datos: RegistroEscuelaCompleto, 
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Jerarquía: Solo el SuperAdmin puede crear usuarios de tipo Escuela.
    """
    # Verificamos el rol del usuario que hace la petición
    if current_user.get("rol") != UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permisos insuficientes. Tu rol es {current_user.get('rol')}, pero se requiere SuperAdmin."
        )

    # 1. Crear Usuario base
    password_hash = get_password_hash(datos.password)
    user_payload = {
        "username": datos.username,
        "passwordhash": password_hash,
        "rol": UserRole.ESCUELA.value
    }

    try:
        # Insertar en la tabla 'usuarios'
        user_res = db.table("usuarios").insert(user_payload).execute()
        if not user_res.data:
            raise Exception("No se pudo crear el usuario base.")
            
        new_user = user_res.data[0]
        id_creado = new_user["idusuario"]

        # 2. Crear Perfil de Escuela vinculado
        escuela_payload = {
            "idusuario": id_creado,
            "nombreescuela": datos.nombre_escuela,
            "direccion": datos.direccion,
            "lema": datos.lema,
            "telefono_oficina": datos.telefono_oficina
        }
        
        db.table("datosescuela").insert(escuela_payload).execute()
        
        return new_user

    except Exception as e:
        print(f"Error DETALLADO en registrar_escuela: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Error en base de datos: {str(e)}"
        )

@router.post("/registrar-profesor", response_model=Usuario, status_code=status.HTTP_201_CREATED)
async def registrar_profesor(
    datos: RegistroProfesorCompleto, 
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Jerarquía: Solo una Escuela puede crear Profesores.
    El profesor se vincula automáticamente a la escuela del usuario creador.
    """
    # Validar que quien crea sea una Escuela
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los usuarios con rol Escuela pueden registrar profesores."
        )

    # Buscar la idescuela del usuario 'Escuela' que está autenticado
    id_usuario_escuela = current_user.get("idusuario")
    escuela_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario_escuela).execute()
    
    if not escuela_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró un perfil de escuela asociado a tu cuenta."
        )
    
    id_escuela_vinculada = escuela_res.data[0]["idescuela"]

    # 1. Crear Usuario Profesor
    password_hash = get_password_hash(datos.password)
    user_payload = {
        "username": datos.username,
        "passwordhash": password_hash,
        "rol": UserRole.PROFESOR.value
    }

    try:
        user_res = db.table("usuarios").insert(user_payload).execute()
        if not user_res.data:
            raise Exception("Error al crear la cuenta de usuario para el profesor.")
            
        new_user = user_res.data[0]

        # 2. Crear Perfil de Profesor vinculado a la escuela
        prof_payload = {
            "idusuario": new_user["idusuario"],
            "idescuela": id_escuela_vinculada,
            "nombrecompleto": datos.nombre_completo,
            "idgradodan": datos.idgradodan
        }
        
        db.table("profesores").insert(prof_payload).execute()
        
        return new_user

    except Exception as e:
        print(f"Error DETALLADO en registrar_profesor: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al vincular profesor: {str(e)}"
        )