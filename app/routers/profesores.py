from fastapi import APIRouter, HTTPException, status
from app.database import supabase
from app.schemas.profesores import ProfesorCreate
from app.utils.security import obtener_password_hash # Importación necesaria
from typing import Optional

router = APIRouter(prefix="/profesores", tags=["Profesores"])

@router.post("/", status_code=status.HTTP_201_CREATED)
async def registrar_profesor(datos: ProfesorCreate):
    """Registra un profesor y encripta su contraseña correctamente."""
    try:
        # 1. Creamos el usuario con el hash de la contraseña
        # Antes se guardaba 'datos.password' directo, ahora usamos la utilidad
        user_data = {
            "username": datos.username,
            "passwordhash": obtener_password_hash(datos.password),
            "rol": "Profesor"
        }
        res_user = supabase.table("usuarios").insert(user_data).execute()
        
        if not res_user.data:
            raise HTTPException(status_code=400, detail="No se pudo crear el acceso")
            
        id_usuario = res_user.data[0]["idusuario"]

        # 2. Vinculamos al profesor con su nueva ID de usuario
        profesor_data = {
            "nombrecompleto": datos.nombrecompleto,
            "idgradodan": datos.idgradodan,
            "idescuela": datos.idescuela,
            "idusuario": id_usuario,
            "estatus": datos.estatus
        }
        res_prof = supabase.table("profesores").insert(profesor_data).execute()
        
        return {"message": "Profesor registrado con éxito y contraseña blindada", "data": res_prof.data[0]}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/")
def listar_profesores(idescuela: Optional[int] = None):
    try:
        query = supabase.table("profesores").select("*, cintasgrados(color, nivelkupdan)")
        if idescuela:
            query = query.eq("idescuela", idescuela)
        res = query.execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))