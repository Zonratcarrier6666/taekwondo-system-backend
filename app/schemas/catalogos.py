from pydantic import BaseModel
from typing import Optional, Any

# Cintas/Grados
class CintasGrados(BaseModel):
    idgrado: int
    nivelkupdan: str
    color: str
    significado: Optional[str] = None

    class Config:
        from_attributes = True

# Datos de la Escuela
class EscuelaBase(BaseModel):
    idusuario: int
    nombreescuela: str
    direccion: Optional[str] = None
    lema: Optional[str] = None
    logo_url: Optional[str] = None
    telefono_oficina: Optional[str] = None
    color_paleta: str = "P-azul"
    config_json: Optional[Any] = None

class Escuela(EscuelaBase):
    idescuela: int
    class Config:
        from_attributes = True