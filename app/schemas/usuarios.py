import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from enum import Enum

# --- ENUMS ---
class UserRole(str, Enum):
    SuperAdmin = "SuperAdmin"
    Escuela = "Escuela"
    Profesor = "Profesor"
    Juez = "Juez"

# --- MODELOS DE AUTENTICACIÓN ---
class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    rol: str
    id_usuario: int
    id_escuela: Optional[int] = None

# --- MODELOS DE REGISTRO CON VALIDACIÓN ESTRICTA ---
class RegistroBase(BaseModel):
    """Base para todos los registros con validación de contraseña compleja."""
    username: str = Field(..., min_length=4)
    password: str = Field(..., min_length=8)

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        # Validación de Mayúscula
        if not any(c.isupper() for c in v):
            raise ValueError('La contraseña debe contener al menos una letra mayúscula.')
        # Validación de Número
        if not any(c.isdigit() for c in v):
            raise ValueError('La contraseña debe contener al menos un número.')
        # Validación de Carácter Especial
        special_chars = r"[$#*&!@%^()+=\[\]{}|;:,.<>?/]"
        if not re.search(special_chars, v):
            raise ValueError('La contraseña debe contener al menos un carácter especial (ej: $#*&).')
        return v

class RegistroEscuela(RegistroBase):
    """Esquema para registrar escuela con la nueva Paleta de Colores."""
    nombre_escuela: str
    direccion: Optional[str] = None
    lema: Optional[str] = None
    telefono_oficina: Optional[str] = None
    # Cambiamos los 3 colores individuales por el identificador de paleta
    color_paleta: str = Field("P-azul", description="ID de la paleta: P-rojo, P-azul, P-verde, etc.")

class RegistroProfesor(RegistroBase):
    nombre_completo: str
    id_grado_dan: int
    id_escuela: int

class RegistroJuez(RegistroBase):
    pass