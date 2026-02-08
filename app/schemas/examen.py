from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List
from datetime import date, datetime

class ExamenBase(BaseModel):
    nombre_examen: str = Field(..., examples=["Examen de Invierno 2025"])
    fecha_programada: date
    lugar: Optional[str] = Field(default="Dojo Central")
    costo_examen: float = Field(default=0.0)
    sinodal: Optional[str] = Field(None, examples=["Mtro. Kim Young"])
    estatus: int = Field(default=1, description="1: Programado, 2: Realizado, 0: Cancelado")

class ExamenCreate(ExamenBase):
    pass

class Examen(ExamenBase):
    idexamen: int
    idescuela: int
    fecharegistro: datetime
    model_config = ConfigDict(from_attributes=True)

# --- Esquemas para Resultados Masivos ---

class ResultadoIndividual(BaseModel):
    """Representa el resultado de un alumno específico en el examen."""
    idalumno: int
    id_nuevo_grado: int
    notas: Optional[str] = "Aprobado en examen masivo"

class CargaResultadosMasivos(BaseModel):
    """Cuerpo de la petición para procesar múltiples alumnos a la vez."""
    fecha_examen: date = Field(default_factory=date.today)
    resultados: List[ResultadoIndividual]