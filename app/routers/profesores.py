from fastapi import APIRouter, HTTPException
from app.database import supabase
from app.schemas import ProfesorCreate
from typing import Optional


router = APIRouter(prefix="/profesores", tags=["Profesores"])

@router.get("/")
def listar_profesores(idescuela: Optional[int] = None):
    """Lista todos los profesores o los filtra por escuela."""
    try:
        query = supabase.table("profesores").select("*, cintasgrados(color, nivelkupdan)")
        if idescuela:
            query = query.eq("idescuela", idescuela)
        
        res = query.execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", status_code=201)
async def registrar_profesor(datos: ProfesorCreate):
    """Crea un usuario y un registro de profesor vinculado a una escuela."""
    try:
        # 1. Crear el usuario con rol 'Profesor'
        user_data = {
            "username": datos.username,
            "passwordhash": datos.password, # TODO: Hash password
            "rol": "Profesor"
        }
        res_user = supabase.table("usuarios").insert(user_data).execute()
        if not res_user.data:
            raise HTTPException(status_code=400, detail="Error al crear usuario para el profesor")
        
        id_usuario = res_user.data[0]["idusuario"]

        # 2. Crear el registro del profesor
        profesor_data = {
            "nombrecompleto": datos.nombrecompleto,
            "idgradodan": datos.idgradodan,
            "idescuela": datos.idescuela,
            "idusuario": id_usuario,
            "estatus": 1
        }
        res_prof = supabase.table("profesores").insert(profesor_data).execute()
        
        return {
            "message": "Profesor dado de alta exitosamente",
            "data": res_prof.data[0]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))