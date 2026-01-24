from pydantic import BaseModel
from typing import Optional

class RegistroEscuelaMaestro(BaseModel):
    # Datos de Usuario Admin
    username: str
    password: str
    
    # Datos de la Institución
    nombre_escuela: str
    direccion: Optional[str] = None
    
    # Datos del Profesor Principal
    nombre_completo_profesor: str
    id_grado_dan: int