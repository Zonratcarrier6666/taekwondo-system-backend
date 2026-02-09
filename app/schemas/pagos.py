from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, List, Any
from datetime import datetime
from enum import IntEnum

class TipoPago(IntEnum):
    MENSUALIDAD = 1
    EXAMEN = 2
    TORNEO = 3
    EQUIPO = 4
    INSCRIPCION_ANUAL = 5

class EstatusPago(IntEnum):
    PENDIENTE = 0
    PAGADO = 1
    CANCELADO = 2

# --- Modelos Auxiliares para Joins ---
class AlumnoResumen(BaseModel):
    nombres: str
    apellidopaterno: str
    apellidomaterno: Optional[str] = None

class DetalleMetodoPago(BaseModel):
    metodo: str
    monto: float

# --- Modelos de Operación ---
class ProcesoPago(BaseModel):
    desglose_pagos: List[DetalleMetodoPago] = Field(..., min_length=1)
    notas: Optional[str] = None

    @property
    def monto_total_recibido(self) -> float:
        return sum(p.monto for p in self.desglose_pagos)

    @property
    def resumen_metodos(self) -> str:
        return " + ".join([f"{p.metodo} (${p.monto})" for p in self.desglose_pagos])

class PagoBase(BaseModel):
    idalumno: int
    monto: float
    concepto: str
    id_tipo_pago: TipoPago = TipoPago.MENSUALIDAD
    id_referencia_evento: Optional[int] = None
    notas_adicionales: Optional[str] = None

class Pago(PagoBase):
    idpago: int
    idescuela: int
    folio_recibo: Optional[str] = None
    estatus: EstatusPago
    metodo_pago: Optional[str] = None
    fecha_pago: Optional[datetime] = None
    fecharegistro: datetime
    url_comprobante: Optional[str] = None
    desglose_interno: Optional[List[dict]] = None
    
    # Campo opcional para cuando hacemos Join con Alumnos
    alumno: Optional[AlumnoResumen] = None

    model_config = ConfigDict(from_attributes=True)