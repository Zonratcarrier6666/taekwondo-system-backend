from pydantic import BaseModel, EmailStr
from datetime import date
from typing import List, Optional

class CategoriaTorneo(BaseModel):
    nombre_categoria: str
    edad_min: int
    edad_max: int
    peso_min: float
    peso_max: float
    grados_permitidos: List[int]
    genero: str

class TorneoCreate(BaseModel):
    nombre: str
    fecha: date
    sede: str
    ubicacion: Optional[str] = None
    modalidades: List[str]
    reglas_categorias: List[CategoriaTorneo]

class InscripcionTorneoCreate(BaseModel):
    idtorneo: int
    idalumno: int
    idprofesor: int 
    peso_declarado: float
    edad_al_momento: int
    correo_confirmacion: EmailStr 

class CheckInCompetidor(BaseModel):
    token_qr: str
    peso_bascula: float