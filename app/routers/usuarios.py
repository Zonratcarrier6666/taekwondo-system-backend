from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client
from typing import List

from app.utils.database import get_db
from app.utils.security import get_password_hash
from app.utils.auth_utils import get_current_user
from app.schemas.usuarios import (
    Usuario, UserRole, RegistroEscuelaCompleto, RegistroProfesorCompleto, RegistroJuez
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
    Incluye validación para evitar nombres de usuario duplicados.
    """
    if current_user.get("rol") != UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permisos insuficientes. Se requiere rol {UserRole.SUPERADMIN}."
        )

    # Validación: Verificar si el nombre de usuario ya existe
    user_check = db.table("usuarios").select("idusuario").eq("username", datos.username).execute()
    if user_check.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario ya está registrado."
        )

    password_hash = get_password_hash(datos.password)
    user_payload = {
        "username": datos.username,
        "passwordhash": password_hash,
        "rol": UserRole.ESCUELA.value
    }

    try:
        user_res = db.table("usuarios").insert(user_payload).execute()
        new_user = user_res.data[0]
        id_creado = new_user["idusuario"]

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
        raise HTTPException(status_code=500, detail=f"Error al registrar escuela: {str(e)}")

@router.post("/registrar-profesor", response_model=Usuario, status_code=status.HTTP_201_CREATED)
async def registrar_profesor(
    datos: RegistroProfesorCompleto, 
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Jerarquía: Solo una Escuela puede crear Profesores.
    El profesor se vincula automáticamente a la escuela del usuario creador.
    Incluye validación para evitar nombres de usuario duplicados.
    """
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo usuarios con rol Escuela pueden registrar profesores."
        )

    # Validación: Verificar si el nombre de usuario ya existe
    user_check = db.table("usuarios").select("idusuario").eq("username", datos.username).execute()
    if user_check.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario ya está registrado."
        )

    id_usuario_escuela = current_user.get("idusuario")
    escuela_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario_escuela).execute()
    
    if not escuela_res.data:
        raise HTTPException(status_code=404, detail="No se encontró perfil de escuela asociado.")
    
    id_escuela_vinculada = escuela_res.data[0]["idescuela"]

    password_hash = get_password_hash(datos.password)
    user_payload = {
        "username": datos.username,
        "passwordhash": password_hash,
        "rol": UserRole.PROFESOR.value
    }

    try:
        user_res = db.table("usuarios").insert(user_payload).execute()
        new_user = user_res.data[0]

        prof_payload = {
            "idusuario": new_user["idusuario"],
            "idescuela": id_escuela_vinculada,
            "nombrecompleto": datos.nombre_completo,
            "idgradodan": datos.idgradodan
        }
        db.table("profesores").insert(prof_payload).execute()
        return new_user
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al registrar profesor: {str(e)}")

@router.post("/registrar-juez", response_model=Usuario, status_code=status.HTTP_201_CREATED)
async def registrar_juez(
    datos: RegistroJuez, 
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Jerarquía: Solo el SuperAdmin puede registrar Jueces.
    Incluye validación para evitar nombres de usuario duplicados.
    """
    if current_user.get("rol") != UserRole.SUPERADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el SuperAdmin puede registrar jueces."
        )

    # Validación: Verificar si el nombre de usuario ya existe
    user_check = db.table("usuarios").select("idusuario").eq("username", datos.username).execute()
    if user_check.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario ya está registrado."
        )

    password_hash = get_password_hash(datos.password)
    user_payload = {
        "username": datos.username,
        "passwordhash": password_hash,
        "rol": UserRole.JUEZ.value
    }

    try:
        user_res = db.table("usuarios").insert(user_payload).execute()
        new_user = user_res.data[0]

        juez_payload = {
            "idusuario": new_user["idusuario"],
            "nombre_completo": datos.nombre_completo
        }
        db.table("jueces").insert(juez_payload).execute()
        return new_user
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al registrar juez: {str(e)}")

@router.get("/perfil", response_model=dict)
async def obtener_mi_perfil(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Retorna la información del usuario logueado y su perfil asociado."""
    return current_user