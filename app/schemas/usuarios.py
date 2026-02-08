from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional
from enum import Enum
from datetime import datetime
import re

class UserRole(str, Enum):
    SUPERADMIN = "SuperAdmin"
    ESCUELA = "Escuela"
    PROFESOR = "Profesor"
    JUEZ = "Juez"

class UsuarioBase(BaseModel):
    # Username: Mínimo 4 caracteres, solo letras, números y guiones bajos
    username: str = Field(..., min_length=4, max_length=20, pattern=r"^[a-zA-Z0-9_]+$")
    rol: UserRole = UserRole.PROFESOR

class UsuarioCreate(UsuarioBase):
    """
    Esquema para creación de usuarios con políticas de contraseña de grado militar.
    """
    password: str = Field(..., min_length=12, max_length=128)

    @field_validator('password')
    @classmethod
    def validar_complejidad_password(cls, v: str) -> str:
        # 1. Comprobar lista negra de palabras comunes
        blacklist = ["password", "contraseña", "12345678", "admin", "taekwondo", "tkd2024", "master"]
        if any(word in v.lower() for word in blacklist):
            raise ValueError('La contraseña es demasiado común o predecible.')

        # 2. Requisitos de caracteres
        if not re.search(r"[A-Z]", v):
            raise ValueError('Debe contener al menos una letra mayúscula.')
        if not re.search(r"[a-z]", v):
            raise ValueError('Debe contener al menos una letra minúscula.')
        if not re.search(r"\d", v):
            raise ValueError('Debe contener al menos un número.')
        if not re.search(r"[!@#$%^&*()_+={}\[\]:;<>,.?/|~-]", v):
            raise ValueError('Debe contener al menos un carácter especial (ej: !@#$%).')
        
        # 3. Comprobar secuencias repetitivas (ej: aaaa, 1111)
        if re.search(r"(.)\1\1\1", v):
            raise ValueError('La contraseña no puede contener caracteres repetidos más de 3 veces consecutivas.')
            
        return v

    @model_validator(mode='after')
    def validar_password_no_es_username(self) -> 'UsuarioCreate':
        """
        Valida que la contraseña no contenga el nombre de usuario por seguridad.
        """
        user = self.username.lower()
        pw = self.password.lower()
        
        if user in pw:
            raise ValueError('La contraseña no puede contener el nombre de usuario.')
            
        return self

# Esquemas de registro especializados (Heredan las validaciones de UsuarioCreate)
class RegistroEscuelaCompleto(UsuarioCreate):
    """Datos para crear un usuario tipo Escuela y su perfil de escuela."""
    nombre_escuela: str = Field(..., min_length=3)
    direccion: Optional[str] = None
    lema: Optional[str] = None
    telefono_oficina: Optional[str] = None

class RegistroProfesorCompleto(UsuarioCreate):
    """Datos para crear un usuario tipo Profesor y su perfil de profesor."""
    nombre_completo: str = Field(..., min_length=5)
    idgradodan: Optional[int] = None
    # El idescuela se obtendrá automáticamente del usuario que registra (si es Escuela)

class RegistroJuez(UsuarioCreate):
    nombre_completo: str = Field(..., min_length=5)

class Usuario(UsuarioBase):
    idusuario: int
    fecha_creacion: datetime
    
    model_config = ConfigDict(from_attributes=True)