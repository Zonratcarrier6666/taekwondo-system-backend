from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

class GenerarMensualidadesBase(BaseModel):
    """Esquema para disparar la creación de deudas mensuales."""
    mes: int = Field(..., ge=1, le=12, examples=[2])
    anio: int = Field(..., ge=2024, le=2030, examples=[2026])
    monto_estandar: float = Field(..., gt=0, description="Monto base de la mensualidad")
    concepto_prefijo: str = Field(default="Mensualidad", examples=["Mensualidad"])
    
    # Nuevo campo configurable
    dia_corte: int = Field(
        default=20, 
        ge=1, 
        le=31, 
        description="Día máximo del mes para cobrarle a un alumno nuevo. Si entró después de este día, no paga este mes."
    )

class ResultadoGeneracion(BaseModel):
    """Resumen de la operación masiva."""
    mes: int
    anio: int
    cargos_creados: int
    alumnos_omitidos: int
    total_monto_proyectado: float