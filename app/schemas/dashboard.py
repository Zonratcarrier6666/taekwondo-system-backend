from pydantic import BaseModel
from typing import List, Dict

class BeltStat(BaseModel):
    color: str
    count: int

class FinanceStat(BaseModel):
    dia: str
    monto: float

class DashboardStats(BaseModel):
    total_alumnos: int
    ingresos_semanales: float
    pagos_pendientes_count: int
    alumnos_torneo_count: int
    distribucion_cintas: List[BeltStat]
    finanzas_semana: List[FinanceStat]
    proximos_torneos: List[dict]

class AsistenciaRegistro(BaseModel):
    idalumno: int
    fecha: str
    presente: bool