from pydantic import BaseModel, EmailStr, Field
from datetime import date
from typing import Optional

class AlumnoCreate(BaseModel):
    # Datos Personales
    nombres: str
    apellidopaterno: str
    apellidomaterno: Optional[str] = None
    fechanacimiento: date
    
    # Contacto y Tutor
    nombretutor: Optional[str] = None
    telefonocontacto: Optional[str] = None
    correotutor: Optional[EmailStr] = None
    direcciondomicilio: Optional[str] = None
    
    # --- INFORMACIÓN MÉDICA (Nueva) ---
    tipo_sangre: Optional[str] = Field(None, example="O+")
    alergias: Optional[str] = "Ninguna"
    padecimientos_cronicos: Optional[str] = "Ninguno"
    seguro_medico: Optional[str] = None
    contacto_emergencia_nombre: Optional[str] = None
    contacto_emergencia_tel: Optional[str] = None
    
    # Datos Académicos
    gradoescolar: Optional[str] = None
    escuelaprocedencia: Optional[str] = None
    idgradoactual: int = 1
    idescuela: int
    fotoalumno: Optional[str] = None
    estatus: int = 1