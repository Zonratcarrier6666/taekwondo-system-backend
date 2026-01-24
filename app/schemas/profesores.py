from pydantic import BaseModel
from typing import Optional

class ProfesorCreate(BaseModel):
    # Datos para crear el acceso (Usuario)
    username: str
    password: str
    # Datos de perfil del profesor
    nombrecompleto: str
    idgradodan: int
    idescuela: int
    estatus: int = 1