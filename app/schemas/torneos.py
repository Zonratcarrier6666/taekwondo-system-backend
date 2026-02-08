from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import date, datetime

# --- Torneo ---
class TorneoBase(BaseModel):
    nombre: str
    fecha: date
    sede: str
    modalidades: Optional[Any] = None # JSONB en SQL
    estatus: Optional[int] = 1

class TorneoCreate(TorneoBase):
    pass

class Torneo(TorneoBase):
    idtorneo: int
    class Config:
        from_attributes = True

# --- Categoría ---
class CategoriaBase(BaseModel):
    idtorneo: int
    nombre_categoria: str
    edad_min: Optional[int] = None
    edad_max: Optional[int] = None
    peso_min: Optional[float] = None
    peso_max: Optional[float] = None
    grados_permitidos: List[int] = [] # ARRAY en SQL
    genero: Optional[str] = None

class CategoriaCreate(CategoriaBase):
    pass

# --- Inscripción ---
class InscripcionBase(BaseModel):
    idtorneo: int
    idalumno: int
    idprofesor: int
    idcategoria: int
    peso_declarado: float
    edad_al_momento: int

class InscripcionCreate(InscripcionBase):
    pass

class Inscripcion(InscripcionBase):
    idinscripcion: int
    token_qr: Optional[str] = None
    estatus_pago: str
    peso_bascula: Optional[float] = None
    estatus_checkin: bool
    fecha_inscripcion: datetime
    class Config:
        from_attributes = True

# --- Combate (Bracket) ---
class CombateBase(BaseModel):
    idtorneo: int
    idcategoria: int
    ronda: int
    area_asignada: Optional[str] = None

class Combate(CombateBase):
    idcombate: int
    id_competidor_1: Optional[int] = None
    id_competidor_2: Optional[int] = None
    id_ganador: Optional[int] = None
    puntos_c1: int = 0
    puntos_c2: int = 0
    id_combate_padre: Optional[int] = None
    posicion_padre: Optional[str] = None
    class Config:
        from_attributes = True