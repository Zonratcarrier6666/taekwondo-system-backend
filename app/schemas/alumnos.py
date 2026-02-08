from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator
from typing import Optional, Any
from datetime import date, datetime

class AlumnoBase(BaseModel):
    """
    Modelo base resiliente. 
    Limpia los nulos de la base de datos antes de la validación.
    """
    nombres: str = Field(..., examples=["Juan Román"])
    apellidopaterno: str = Field(..., examples=["Riquelme"])
    apellidomaterno: str = Field(default="N/A")
    fechanacimiento: date = Field(..., examples=["2010-10-10"])
    
    contacto_emergencia_nombre: str = Field(default="Desconocido")
    contacto_emergencia_tel: str = Field(default="Sin Teléfono")
    
    nombretutor: str = Field(default="Desconocido")
    telefonocontacto: str = Field(default="Sin Teléfono")
    correotutor: Optional[EmailStr] = Field(default=None)
    direcciondomicilio: str = Field(default="Domicilio Desconocido")
    
    grado_escolar: str = Field(default="Desconocido")
    escuela_procedencia: str = Field(default="Ninguna")
    fotoalumno: str = Field(default="")
    
    tipo_sangre: str = Field(default="S/D")
    alergias: str = Field(default="Ninguna")
    padecimientos_cronicos: str = Field(default="Ninguno")
    seguro_medico: str = Field(default="No cuenta")
    nss_o_poliza: str = Field(default="N/A")
    
    idgradoactual: int = Field(default=1)
    idescuela: Optional[int] = None
    idprofesor: Optional[int] = None

    # --- LIMPIADOR DE DATOS NULOS ---
    @field_validator(
        "apellidomaterno", "contacto_emergencia_nombre", "contacto_emergencia_tel",
        "nombretutor", "telefonocontacto", "direcciondomicilio", "grado_escolar",
        "escuela_procedencia", "fotoalumno", "tipo_sangre", "alergias",
        "padecimientos_cronicos", "seguro_medico", "nss_o_poliza",
        mode="before"
    )
    @classmethod
    def convert_null_to_string(cls, v: Any) -> str:
        """Convierte cualquier NULL de la BD en un string vacío para evitar errores."""
        if v is None:
            return ""
        return str(v)

class AlumnoCreate(AlumnoBase):
    """
    Reglas estrictas para REGISTROS NUEVOS. 
    Aquí sí obligamos a que el usuario mande datos de calidad.
    """
    nombres: str = Field(..., min_length=2)
    apellidopaterno: str = Field(..., min_length=2)
    direcciondomicilio: str = Field(..., min_length=10)
    contacto_emergencia_nombre: str = Field(..., min_length=5)
    contacto_emergencia_tel: str = Field(..., min_length=10)

class AlumnoUpdate(BaseModel):
    """Esquema para actualizaciones parciales del perfil."""
    nombres: Optional[str] = None
    apellidopaterno: Optional[str] = None
    apellidomaterno: Optional[str] = None
    idgradoactual: Optional[int] = None
    estatus: Optional[int] = None
    fotoalumno: Optional[str] = None
    contacto_emergencia_nombre: Optional[str] = None
    contacto_emergencia_tel: Optional[str] = None
    grado_escolar: Optional[str] = None
    escuela_procedencia: Optional[str] = None
    direcciondomicilio: Optional[str] = None
    telefonocontacto: Optional[str] = None
    correotutor: Optional[EmailStr] = None

class AlumnoFotoUpdate(BaseModel):
    """Esquema específico para actualizar únicamente la fotografía del alumno."""
    fotoalumno: str = Field(..., description="URL de la imagen almacenada o string en formato Base64", examples=["https://storage.googleapis.com/tu-bucket/foto.jpg"])

class Alumno(AlumnoBase):
    """Representación final para la API."""
    idalumno: int
    fecharegistro: datetime
    model_config = ConfigDict(from_attributes=True)