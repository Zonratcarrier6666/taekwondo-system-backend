from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Any

# Datos de la Escuela
class EscuelaBase(BaseModel):
    idusuario: int
    nombreescuela: str
    direccion: Optional[str] = None
    lema: Optional[str] = None
    logo_url: Optional[str] = None
    correo_escuela: Optional[EmailStr] = None # Nuevo campo con validación de email
    telefono_oficina: Optional[str] = None
    color_paleta: str = "P-azul"
    config_json: Optional[Any] = None

# Esquema para actualización parcial
class EscuelaUpdate(BaseModel):
    nombreescuela: Optional[str] = Field(None, min_length=3)
    direccion: Optional[str] = None
    lema: Optional[str] = None
    correo_escuela: Optional[EmailStr] = None # Permitir actualizar el correo
    telefono_oficina: Optional[str] = None
    color_paleta: Optional[str] = None 

class Escuela(EscuelaBase):
    idescuela: int
    class Config:
        from_attributes = True