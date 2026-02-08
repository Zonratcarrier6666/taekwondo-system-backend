from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import date, datetime

# --- Catálogo de Cintas ---
class CintaBase(BaseModel):
    nivelkupdan: str = Field(..., examples=["10mo Kup", "1er Dan"])
    color: str = Field(..., examples=["Blanca", "Negra"])
    significado: Optional[str] = Field(None, examples=["Pureza e inocencia"])

class Cinta(CintaBase):
    idgrado: int
    model_config = ConfigDict(from_attributes=True)

# --- Proceso de Promoción ---
class PromocionAlumno(BaseModel):
    id_nuevo_grado: int = Field(..., description="ID del grado al que asciende")
    fecha_examen: date = Field(default_factory=date.today)
    notas: Optional[str] = Field(default="Examen de promoción regular")

# --- Historial ---
class HistorialGradoBase(BaseModel):
    idalumno: int
    idgrado_anterior: int
    idgrado_nuevo: int
    fecha_examen: date
    idprofesor_evaluador: Optional[int] = None
    notas: Optional[str] = None

class HistorialGrado(HistorialGradoBase):
    idhistorial: int
    fecharegistro: datetime
    # Relaciones para mostrar nombres en el GET
    grado_anterior: Optional[Cinta] = None
    grado_nuevo: Optional[Cinta] = None

    model_config = ConfigDict(from_attributes=True)