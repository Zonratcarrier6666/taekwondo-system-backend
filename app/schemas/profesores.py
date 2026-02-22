from pydantic import BaseModel, ConfigDict, Field, EmailStr
from typing import Optional, List
from datetime import datetime

class ProfesorBase(BaseModel):
    """
    Representa los campos base de la tabla 'profesores' en Supabase.
    """
    nombrecompleto: str = Field(..., examples=["Lucas Martínez"])
    email: Optional[EmailStr] = Field(None, examples=["maestro@dojo.com"])
    telefono: Optional[str] = Field(None, max_length=15)
    # Se elimina la restricción le=9 para permitir grados mayores registrados en la BD (ej. 11)
    idgradodan: int = Field(default=1, ge=1)
    foto_url: Optional[str] = Field(default="", description="URL de la foto de perfil almacenada en Storage")
    estatus: int = Field(default=1, description="1: Activo, 0: Inactivo")

class ProfesorCreate(ProfesorBase):
    """
    Esquema utilizado para la creación inicial del perfil del profesor.
    Requiere la vinculación manual con el usuario y la escuela.
    """
    idusuario: int
    idescuela: int

class ProfesorUpdate(BaseModel):
    """
    Permite la actualización parcial de los campos permitidos.
    """
    nombrecompleto: Optional[str] = None
    email: Optional[EmailStr] = None
    telefono: Optional[str] = None
    idgradodan: Optional[int] = None
    estatus: Optional[int] = None
    foto_url: Optional[str] = None

class Profesor(ProfesorBase):
    """
    Modelo completo que representa un registro extraído de la base de datos.
    """
    idprofesor: int
    idusuario: int
    idescuela: int
    fecharegistro: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)