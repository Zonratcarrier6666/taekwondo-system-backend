from pydantic import BaseModel
from typing import Optional

class CintaRead(BaseModel):
    idgrado: int
    nivelkupdan: str
    color: str
    significado: Optional[str] = None
    
    