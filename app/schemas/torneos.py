from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Any
from datetime import date, datetime

# --- Esquemas para Torneos (Tabla public.torneos) ---

class TorneoBase(BaseModel):
    nombre: str = Field(..., examples=["Open Nacional de Taekwondo 2026"])
    fecha: date
    sede: str = Field(..., examples=["Auditorio Municipal, CDMX"])
    modalidades: Optional[dict] = Field(default=None, description="JSON con modalidades: Combate, Poomsae, etc.")
    costo_inscripcion: float = Field(default=0.0, gt=-1) # Aunque no se ve en la foto, lo mantenemos para finanzas
    estatus: int = Field(default=1, description="1: Abierto, 2: En curso, 3: Finalizado, 0: Cancelado")

class TorneoCreate(TorneoBase):
    pass

class Torneo(TorneoBase):
    idtorneo: int
    fecharegistro: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

# --- Esquemas para Categorías (Tabla public.torneo_categorias) ---

class CategoriaTorneoBase(BaseModel):
    idtorneo: int
    nombre_categoria: str = Field(..., examples=["Juvenil Pesado Masculino"])
    edad_min: int = Field(default=0)
    edad_max: int = Field(default=99)
    peso_min: float = Field(default=0.0)
    peso_max: float = Field(default=999.0)
    grados_permitidos: List[int] = Field(default=[], description="Array de IDs de cintas permitidas")
    genero: str = Field(..., examples=["Masculino", "Femenino", "Mixto"])

class CategoriaTorneoCreate(CategoriaTorneoBase):
    pass

class CategoriaTorneo(CategoriaTorneoBase):
    idcategoria: int
    model_config = ConfigDict(from_attributes=True)

# --- Esquema para Inscripción ---

class AlumnoInscripcion(BaseModel):
    """Datos mínimos para inscribir a un alumno."""
    idalumno: int
    idcategoria: int
    peso_declarado: float = Field(..., gt=0, examples=[55.5])

class InscripcionTorneo(BaseModel):
    """Lista de alumnos a inscribir."""
    inscripciones: List[AlumnoInscripcion]