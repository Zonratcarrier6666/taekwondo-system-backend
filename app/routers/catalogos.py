from fastapi import APIRouter, HTTPException
from app.utils.database import supabase

router = APIRouter(prefix="/catalogos", tags=["Catálogos"])

@router.get("/cintas")
def obtener_todas_las_cintas():
    """Trae la lista completa de grados de la base de datos."""
    try:
        # En Postgres/Supabase usamos nombres en minúsculas
        res = supabase.table("cintasgrados").select("*").execute()
        return res.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))