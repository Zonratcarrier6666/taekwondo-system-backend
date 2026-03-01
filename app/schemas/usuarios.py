from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime
import re

from app.schemas.roles import UserRole   # ← viene de roles.py, no circular

class UsuarioBase(BaseModel):
    username: str = Field(..., min_length=4, max_length=20, pattern=r"^[a-zA-Z0-9_]+$")
    rol: UserRole = UserRole.PROFESOR

class UsuarioCreate(UsuarioBase):
    password: str = Field(..., min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def validar_complejidad_password(cls, v: str) -> str:
        blacklist = ["password", "contraseña", "12345678", "admin", "taekwondo", "tkd2024", "master"]
        if any(word in v.lower() for word in blacklist):
            raise ValueError("La contraseña es demasiado común o predecible.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Debe contener al menos una letra mayúscula.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Debe contener al menos una letra minúscula.")
        if not re.search(r"\d", v):
            raise ValueError("Debe contener al menos un número.")
        if not re.search(r"[!@#$%^&*()_+={}\[\]:;<>,.?/|~-]", v):
            raise ValueError("Debe contener al menos un carácter especial (!@#$%).")
        if re.search(r"(.)\1\1\1", v):
            raise ValueError("No puede contener caracteres repetidos más de 3 veces.")
        return v

    @model_validator(mode="after")
    def validar_password_no_es_username(self) -> "UsuarioCreate":
        if self.username.lower() in self.password.lower():
            raise ValueError("La contraseña no puede contener el nombre de usuario.")
        return self

class RegistroEscuelaCompleto(UsuarioCreate):
    nombre_escuela:   str           = Field(..., min_length=3)
    direccion:        Optional[str] = None
    lema:             Optional[str] = None
    telefono_oficina: Optional[str] = None

class RegistroProfesorCompleto(UsuarioCreate):
    nombre_completo: str           = Field(..., min_length=5)
    idgradodan:      Optional[int] = None
    idescuela:       Optional[int] = None   # requerido si lo crea SuperAdmin

class RegistroJuez(UsuarioCreate):
    nombre_completo: str = Field(..., min_length=5)

class RegistroStaff(UsuarioCreate):
    nombre_completo: str           = Field(..., min_length=5)
    idescuela:       Optional[int] = None

class Usuario(UsuarioBase):
    idusuario:      int
    fecha_creacion: datetime
    model_config = ConfigDict(from_attributes=True)