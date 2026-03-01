# ============================================================
#  app/schemas/torneos.py
# ============================================================

from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, Literal
from datetime import date, datetime
from enum import IntEnum, Enum


class EstatusTorneo(str, Enum):
    PROXIMO    = "proximo"
    EN_CURSO   = "en_curso"
    FINALIZADO = "finalizado"
    CANCELADO  = "cancelado"

class EstatusInscripcion(str, Enum):
    PENDIENTE_PAGO = "pendiente_pago"
    PAGADO         = "pagado"
    CANCELADO      = "cancelado"

class GeneroFiltro(str, Enum):
    MASCULINO = "M"
    FEMENINO  = "F"
    AMBOS     = "A"


# ─── Crear / Editar Torneo ───────────────────────────────────

class CrearTorneo(BaseModel):
    nombre:           str
    fecha:            str                    # "YYYY-MM-DD"
    hora_inicio:      str = "09:00"          # "HH:MM"
    sede:             str
    ciudad:           str
    monto_inscripcion: float

    # Requisitos de elegibilidad
    cinta_minima:     Optional[int] = None   # idcinta mínima
    cinta_maxima:     Optional[int] = None   # idcinta máxima
    edad_minima:      Optional[int] = None
    edad_maxima:      Optional[int] = None
    peso_minimo:      Optional[float] = None  # kg
    peso_maximo:      Optional[float] = None  # kg
    genero:           GeneroFiltro = GeneroFiltro.AMBOS

    descripcion:      Optional[str] = None
    max_participantes: Optional[int] = None

    @field_validator("monto_inscripcion")
    @classmethod
    def monto_pos(cls, v):
        if v < 0: raise ValueError("El monto no puede ser negativo")
        return v

    @field_validator("fecha")
    @classmethod
    def fecha_valida(cls, v):
        try: datetime.strptime(v, "%Y-%m-%d")
        except: raise ValueError("Formato de fecha: YYYY-MM-DD")
        return v


class EditarTorneo(BaseModel):
    nombre:            Optional[str]   = None
    fecha:             Optional[str]   = None
    hora_inicio:       Optional[str]   = None
    sede:              Optional[str]   = None
    ciudad:            Optional[str]   = None
    monto_inscripcion: Optional[float] = None
    cinta_minima:      Optional[int]   = None
    cinta_maxima:      Optional[int]   = None
    edad_minima:       Optional[int]   = None
    edad_maxima:       Optional[int]   = None
    peso_minimo:       Optional[float] = None
    peso_maximo:       Optional[float] = None
    genero:            Optional[GeneroFiltro] = None
    descripcion:       Optional[str]   = None
    max_participantes: Optional[int]   = None
    estatus:           Optional[EstatusTorneo] = None


# ─── Inscripción ─────────────────────────────────────────────

class InscribirAlumno(BaseModel):
    idtorneo:  int
    idalumno:  int
    peso_actual: Optional[float] = None   # kg — se registra al inscribir


class InscribirAlumnosLote(BaseModel):
    idtorneo:   int
    idalumnos:  list[int]
    peso_actual: Optional[float] = None   # peso default si no se especifica por alumno


class InscribirAlumnosConPeso(BaseModel):
    """Para inscribir con peso individual por alumno."""
    idtorneo: int
    alumnos:  list[dict]   # [{"idalumno": 1, "peso_actual": 52.5}, ...]


# ─── QR ──────────────────────────────────────────────────────

class ValidarQR(BaseModel):
    token: str   # UUID del QR escaneado


# ─── Matchmaking ─────────────────────────────────────────────

class GenerarMatchmaking(BaseModel):
    idtorneo:          int
    solo_asistentes:   bool = True    # True = solo los que llegaron, False = todos los inscritos pagados


# ─── Responses ───────────────────────────────────────────────

class TorneoResponse(BaseModel):
    idtorneo:          int
    nombre:            str
    fecha:             str
    hora_inicio:       str
    sede:              str
    ciudad:            str
    monto_inscripcion: float
    cinta_minima:      Optional[int]
    cinta_maxima:      Optional[int]
    edad_minima:       Optional[int]
    edad_maxima:       Optional[int]
    peso_minimo:       Optional[float]
    peso_maximo:       Optional[float]
    genero:            str
    estatus:           str
    descripcion:       Optional[str]
    max_participantes: Optional[int]
    total_inscritos:   int = 0


class AlumnoElegibleResponse(BaseModel):
    idalumno:       int
    nombres:        str
    apellidopaterno: str
    edad:           int
    cinta:          str
    color_cinta:    str
    peso:           Optional[float]
    genero:         Optional[str]
    ya_inscrito:    bool


class InscripcionResponse(BaseModel):
    idinscripcion:  int
    idalumno:       int
    nombre_alumno:  str
    cinta:          str
    edad:           int
    peso:           Optional[float]
    genero:         Optional[str]
    estatus_pago:   str
    qr_generado:    bool
    qr_usado:       bool
    fecha_inscripcion: str


class ValidarQRResponse(BaseModel):
    ok:             bool
    idalumno:       int
    nombre_alumno:  str
    torneo:         str
    mensaje:        str


class MatchResponse(BaseModel):
    categoria:      str    # "Masculino | Cinta Roja | 12-14 años | 45-50 kg"
    participantes:  list[dict]
    enfrentamientos: list[dict]  # [{"alumno_a": {...}, "alumno_b": {...}}]