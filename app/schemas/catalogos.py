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

