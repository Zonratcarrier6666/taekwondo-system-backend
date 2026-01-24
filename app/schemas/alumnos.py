from pydantic import BaseModel, EmailStr
from datetime import date
from typing import Optional

class AlumnoCreate(BaseModel):
    nombres: str
    apellidopaterno: str
    apellidomaterno: Optional[str] = None
    fechanacimiento: date
    nombretutor: Optional[str] = None
    telefonocontacto: Optional[str] = None
    correotutor: Optional[EmailStr] = None
    direcciondomicilio: Optional[str] = None
    gradoescolar: Optional[str] = None
    escuelaprocedencia: Optional[str] = None
    idgradoactual: int = 1
    idescuela: int
    fotoalumno: Optional[str] = None
    estatus: int = 1