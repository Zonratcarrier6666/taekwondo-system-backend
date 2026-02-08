from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime

class ProfesorBase(BaseModel):
    idusuario: int
    idescuela: int
    idgradodan: Optional[int] = Field(None, examples=[4])
    nombrecompleto: str = Field(..., examples=["Lucas Martínez"])
    foto_url: Optional[str] = Field(default="", description="URL de la foto de perfil")
    estatus: Optional[int] = 1

class ProfesorCreate(ProfesorBase):
    pass

class ProfesorUpdate(BaseModel):
    idgradodan: Optional[int] = None
    nombrecompleto: Optional[str] = None
    estatus: Optional[int] = None
    foto_url: Optional[str] = None

class Profesor(ProfesorBase):
    idprofesor: int

    model_config = ConfigDict(from_attributes=True)