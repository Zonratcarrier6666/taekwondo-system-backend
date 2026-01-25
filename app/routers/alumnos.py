from fastapi import APIRouter, HTTPException, status
from app.database import supabase
from app.schemas.alumnos import AlumnoCreate
from typing import Optional

router = APIRouter(prefix="/alumnos", tags=["Alumnos"])

@router.get("/")
def listar_alumnos(idescuela: Optional[int] = None):
    """Obtiene los alumnos. Si se pasa idescuela, filtra por ella."""
    try:
        query = supabase.table("alumnos").select("*")
        if idescuela:
            query = query.eq("idescuela", idescuela)
        res = query.execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", status_code=status.HTTP_201_CREATED)
async def registrar_alumno(alumno: AlumnoCreate):
    """Crea un nuevo alumno incluyendo su ficha médica."""
    try:
        datos = alumno.model_dump(mode="json")
        res = supabase.table("alumnos").insert(datos).execute()
        
        if not res.data:
            raise HTTPException(status_code=400, detail="Error al registrar en la base de datos")
            
        return {"status": "success", "message": "Alumno y ficha médica creados", "alumno": res.data[0]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))