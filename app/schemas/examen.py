from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import date, datetime

class ExamenBase(BaseModel):
    """Información fundamental de un evento de examen."""
    nombre_examen: str = Field(..., examples=["Examen de Invierno 2025"])
    fecha_programada: date
    lugar: Optional[str] = Field(default="Dojo Central")
    costo_examen: float = Field(default=0.0, description="Costo que se cobrará al asignar el examen")
    sinodal: Optional[str] = Field(None, examples=["Mtro. Kim Young"])
    estatus: int = Field(default=1, description="1: Programado, 2: Realizado, 0: Cancelado")

class ExamenCreate(ExamenBase):
    pass

class Examen(ExamenBase):
    idexamen: int
    idescuela: int
    fecharegistro: datetime
    model_config = ConfigDict(from_attributes=True)

# --- NUEVO: Esquema para Asignación ---

class AsignacionExamen(BaseModel):
    """Lista de IDs de alumnos que presentarán el examen."""
    alumnos_ids: List[int]

# --- Esquemas para Resultados ---

class ResultadoIndividual(BaseModel):
    """Datos de aprobación para un alumno que YA PAGÓ."""
    idalumno: int
    id_nuevo_grado: int
    notas: Optional[str] = Field(default="Aprobado")

class CargaResultadosMasivos(BaseModel):
    fecha_examen: date = Field(default_factory=date.today)
    resultados: List[ResultadoIndividual]

# --- Esquema para Promoción Manual (Individual) ---

class PromocionManual(BaseModel):
    """
    Esquema para subir a un alumno de grado sin un evento de examen previo.
    Permite generar un cobro administrativo opcional.
    """
    idalumno: int
    id_nuevo_grado: int = Field(..., description="ID de la nueva cinta")
    fecha_promocion: date = Field(default_factory=date.today)
    monto: float = Field(default=0.0, description="Costo administrativo u honorarios del cambio de cinta")
    notas: Optional[str] = Field(default="Promoción administrativa manual")