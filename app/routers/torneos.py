from fastapi import APIRouter, HTTPException, Header
from app.database import supabase
from app.schemas.usuarios import RegistroEscuela, RegistroProfesor, RegistroJuez, UserRole
from typing import Optional

router = APIRouter(prefix="/usuarios", tags=["Gestión de Usuarios"])

@router.post("/registrar-escuela")
async def crear_escuela(datos: RegistroEscuela, x_user_role: str = Header(...)):
    """Solo el SuperAdmin puede dar de alta Escuelas (Dueños)."""
    if x_user_role != UserRole.SuperAdmin:
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar escuelas")
    
    try:
        # 1. Crear Usuario
        user_res = supabase.table("usuarios").insert({
            "username": datos.username,
            "passwordhash": datos.password,
            "rol": UserRole.Escuela
        }).execute()
        
        id_usuario = user_res.data[0]["idusuario"]
        
        # 2. Crear Datos de Escuela
        escuela_res = supabase.table("datosescuela").insert({
            "idusuario": id_usuario,
            "nombreescuela": datos.nombre_escuela,
            "direccion": datos.direccion,
            "lema": datos.lema,
            "telefono_oficina": datos.telefono_oficina
        }).execute()
        
        return {"message": "Escuela registrada exitosamente", "data": escuela_res.data[0]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/registrar-profesor")
async def crear_profesor(datos: RegistroProfesor, x_user_role: str = Header(...), x_user_id_escuela: Optional[int] = Header(None)):
    """SuperAdmin y Escuela pueden registrar Profesores."""
    if x_user_role not in [UserRole.SuperAdmin, UserRole.Escuela]:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")
    
    if x_user_role == UserRole.Escuela and x_user_id_escuela != datos.id_escuela:
        raise HTTPException(status_code=403, detail="Solo puedes registrar profesores para tu propia escuela")

    try:
        user_res = supabase.table("usuarios").insert({
            "username": datos.username,
            "passwordhash": datos.password,
            "rol": UserRole.Profesor
        }).execute()
        
        id_usuario = user_res.data[0]["idusuario"]
        
        prof_res = supabase.table("profesores").insert({
            "idusuario": id_usuario,
            "idescuela": datos.id_escuela,
            "idgradodan": datos.id_grado_dan,
            "nombrecompleto": datos.nombre_completo
        }).execute()
        
        return {"message": "Profesor registrado exitosamente", "data": prof_res.data[0]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/registrar-juez")
async def crear_juez(datos: RegistroJuez, x_user_role: str = Header(...)):
    """Solo el SuperAdmin puede dar de alta Jueces de Torneo."""
    if x_user_role != UserRole.SuperAdmin:
        raise HTTPException(status_code=403, detail="Solo el administrador global puede crear jueces")
    
    try:
        res = supabase.table("usuarios").insert({
            "username": datos.username,
            "passwordhash": datos.password,
            "rol": UserRole.Juez
        }).execute()
        return {"message": "Juez creado exitosamente", "user": res.data[0]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))