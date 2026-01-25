from fastapi import APIRouter, HTTPException, Header, status
from app.database import supabase
from app.schemas.usuarios import RegistroEscuela, RegistroProfesor, RegistroJuez, UserRole
from app.utils.security import obtener_password_hash
from typing import Optional

router = APIRouter(prefix="/usuarios", tags=["Gestión de Usuarios"])

@router.post("/registrar-escuela", status_code=status.HTTP_201_CREATED)
async def crear_escuela(datos: RegistroEscuela, x_user_role: str = Header(...)):
    """Registro de Escuela con sistema de Paletas y Hash de password."""
    if x_user_role != UserRole.SuperAdmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Operación exclusiva para el SuperAdmin."
        )
    
    try:
        # 1. Encriptar contraseña
        password_hasheada = obtener_password_hash(datos.password)
        
        # 2. Insertar en tabla Usuarios
        user_res = supabase.table("usuarios").insert({
            "username": datos.username,
            "passwordhash": password_hasheada,
            "rol": UserRole.Escuela
        }).execute()
        
        if not user_res.data:
            raise HTTPException(status_code=400, detail="Error al crear usuario de acceso.")
            
        id_usuario = user_res.data[0]["idusuario"]
        
        # 3. Insertar en tabla DatosEscuela con el campo color_paleta
        escuela_res = supabase.table("datosescuela").insert({
            "idusuario": id_usuario,
            "nombreescuela": datos.nombre_escuela,
            "direccion": datos.direccion,
            "lema": datos.lema,
            "telefono_oficina": datos.telefono_oficina,
            "color_paleta": datos.color_paleta # Nuevo campo sincronizado con la BD
        }).execute()
        
        return {
            "message": "Escuela registrada exitosamente", 
            "escuela": escuela_res.data[0],
            "paleta_asignada": datos.color_paleta
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/registrar-profesor")
async def crear_profesor(datos: RegistroProfesor, x_user_role: str = Header(...)):
    """Registro de profesor con validación de seguridad y hash."""
    if x_user_role not in [UserRole.SuperAdmin, UserRole.Escuela]:
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar staff.")

    try:
        user_res = supabase.table("usuarios").insert({
            "username": datos.username,
            "passwordhash": obtener_password_hash(datos.password),
            "rol": UserRole.Profesor
        }).execute()
        
        id_usuario = user_res.data[0]["idusuario"]
        
        prof_res = supabase.table("profesores").insert({
            "idusuario": id_usuario,
            "idescuela": datos.id_escuela,
            "idgradodan": datos.id_grado_dan,
            "nombrecompleto": datos.nombre_completo
        }).execute()
        
        return {"message": "Profesor registrado y vinculado correctamente.", "data": prof_res.data[0]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))