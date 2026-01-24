from fastapi import APIRouter, HTTPException
from app.database import supabase
from app.schemas import AlumnoCreate

router = APIRouter(prefix="/alumnos", tags=["Alumnos"])

@router.get("/")
def listar_alumnos():
    """Obtiene todos los alumnos registrados."""
    try:
        res = supabase.table("alumnos").select("*").execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", status_code=201)
async def registrar_alumno(alumno: AlumnoCreate):
    """Crea un nuevo alumno vinculándolo a una escuela."""
    try:
        # Usamos mode="json" para serializar las fechas correctamente
        datos = alumno.model_dump(mode="json")
        res = supabase.table("alumnos").insert(datos).execute()
        
        if not res.data:
            raise HTTPException(status_code=400, detail="No se pudo registrar el alumno")
            
        return {"status": "success", "alumno": res.data[0]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))