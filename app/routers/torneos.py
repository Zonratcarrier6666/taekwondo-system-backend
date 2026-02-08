from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from supabase import Client

# Usamos importaciones absolutas para mantener la consistencia en el backend
from app.utils.database import get_db
from app.schemas.torneos import Torneo, TorneoCreate, CategoriaCreate, Inscripcion, InscripcionCreate
from app.schemas.usuarios import UserRole # Importamos lo que el error solicitaba

router = APIRouter()

@router.get("/", response_model=List[Torneo])
def listar_torneos(db: Client = Depends(get_db)):
    """Obtiene la lista de todos los torneos."""
    result = db.table("torneos").select("*").execute()
    return result.data

@router.post("/", response_model=Torneo, status_code=status.HTTP_201_CREATED)
def crear_torneo(torneo: TorneoCreate, db: Client = Depends(get_db)):
    """Crea un nuevo evento de torneo."""
    result = db.table("torneos").insert(torneo.model_dump()).execute()
    return result.data[0]

@router.post("/inscripciones", response_model=Inscripcion)
def inscribir_alumno(inscripcion: InscripcionCreate, db: Client = Depends(get_db)):
    """Inscribe a un alumno en una categoría específica de un torneo."""
    try:
        # Generamos un token QR simple (esto se puede mejorar luego)
        datos = inscripcion.model_dump()
        datos["token_qr"] = f"T{inscripcion.idtorneo}-A{inscripcion.idalumno}-{datetime.now().timestamp()}"
        
        result = db.table("inscripciones_torneo").insert(datos).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))