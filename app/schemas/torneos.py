# ============================================================
#  app/schemas/torneos.py  — v2
#  Agrega: tipo_torneo, areas, checkin, modalidad local
# ============================================================

from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum


class EstatusTorneo(str, Enum):
    PROXIMO    = "proximo"
    EN_CURSO   = "en_curso"
    FINALIZADO = "finalizado"
    CANCELADO  = "cancelado"

class TipoTorneo(str, Enum):
    COMPETENCIA = "competencia"   # 1 ganador, eliminación directa
    LOCAL       = "local"         # 1°/2°/3°, máx 3 combates, matchmaking flexible

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
    nombre:            str
    fecha:             str           # "YYYY-MM-DD"
    hora_inicio:       str = "09:00"
    sede:              str
    ciudad:            str
    monto_inscripcion: float

    # NUEVO: tipo de torneo
    tipo_torneo:       TipoTorneo = TipoTorneo.COMPETENCIA

    # NUEVO: áreas/rings de la sede
    num_areas:         int = 1

    # NUEVO: límite de combates por competidor (local = 3, competencia = sin límite)
    max_combates_por_competidor: int = 3

    # Requisitos de elegibilidad
    cinta_minima:      Optional[int]   = None
    cinta_maxima:      Optional[int]   = None
    edad_minima:       Optional[int]   = None
    edad_maxima:       Optional[int]   = None
    peso_minimo:       Optional[float] = None
    peso_maximo:       Optional[float] = None
    genero:            GeneroFiltro = GeneroFiltro.AMBOS

    descripcion:       Optional[str] = None
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

    @field_validator("num_areas")
    @classmethod
    def areas_validas(cls, v):
        if v < 1: raise ValueError("Debe haber al menos 1 área de combate")
        if v > 20: raise ValueError("Máximo 20 áreas por torneo")
        return v


class EditarTorneo(BaseModel):
    nombre:                      Optional[str]         = None
    fecha:                       Optional[str]         = None
    hora_inicio:                 Optional[str]         = None
    sede:                        Optional[str]         = None
    ciudad:                      Optional[str]         = None
    monto_inscripcion:           Optional[float]       = None
    tipo_torneo:                 Optional[TipoTorneo]  = None
    num_areas:                   Optional[int]         = None
    max_combates_por_competidor: Optional[int]         = None
    cinta_minima:                Optional[int]         = None
    cinta_maxima:                Optional[int]         = None
    edad_minima:                 Optional[int]         = None
    edad_maxima:                 Optional[int]         = None
    peso_minimo:                 Optional[float]       = None
    peso_maximo:                 Optional[float]       = None
    genero:                      Optional[GeneroFiltro]= None
    descripcion:                 Optional[str]         = None
    max_participantes:           Optional[int]         = None
    estatus:                     Optional[EstatusTorneo] = None


# ─── Áreas de combate ────────────────────────────────────────

class CrearArea(BaseModel):
    nombre_area:     str
    idjuez_asignado: Optional[int] = None

class EditarArea(BaseModel):
    nombre_area:     Optional[str] = None
    idjuez_asignado: Optional[int] = None
    estatus:         Optional[str] = None  # disponible | en_combate | inactiva


# ─── Inscripción ─────────────────────────────────────────────

class InscribirAlumno(BaseModel):
    idtorneo:    int
    idalumno:    int
    peso_actual: Optional[float] = None

class InscribirAlumnosLote(BaseModel):
    idtorneo:    int
    idalumnos:   list[int]
    peso_actual: Optional[float] = None

class InscribirAlumnosConPeso(BaseModel):
    idtorneo: int
    alumnos:  list[dict]   # [{"idalumno": 1, "peso_actual": 52.5}, ...]


# ─── Check-in ────────────────────────────────────────────────

class CheckinLote(BaseModel):
    idinscripciones: list[int]


# ─── QR ──────────────────────────────────────────────────────

class ValidarQR(BaseModel):
    token:  str
    idarea: Optional[int] = None   # área donde se escanea


# ─── Matchmaking ─────────────────────────────────────────────

class GenerarMatchmaking(BaseModel):
    idtorneo:        int
    solo_asistentes: bool = True

class ReasignarMatchmaking(BaseModel):
    idinscripcion_a: int
    idinscripcion_b: int


# ─── Resultado combate ───────────────────────────────────────

class ResultadoLocal(BaseModel):
    """Modalidad local — el juez solo dice quién ganó, sin puntos."""
    id_ganador: int   # idinscripcion del ganador

class AsignarPodio(BaseModel):
    """Asignación manual de 1°/2°/3° en torneo local."""
    podio: list[dict]   # [{"idinscripcion": 5, "lugar": 1}, ...]


# ─── Responses ───────────────────────────────────────────────

class TorneoResponse(BaseModel):
    idtorneo:                    int
    nombre:                      str
    fecha:                       str
    hora_inicio:                 str
    sede:                        str
    ciudad:                      str
    monto_inscripcion:           float
    tipo_torneo:                 str
    num_areas:                   int
    max_combates_por_competidor: int
    cinta_minima:                Optional[int]
    cinta_maxima:                Optional[int]
    edad_minima:                 Optional[int]
    edad_maxima:                 Optional[int]
    peso_minimo:                 Optional[float]
    peso_maximo:                 Optional[float]
    genero:                      str
    estatus:                     str
    descripcion:                 Optional[str]
    max_participantes:           Optional[int]
    total_inscritos:             int = 0


class AreaResponse(BaseModel):
    idarea:              int
    nombre_area:         str
    estatus:             str
    idjuez_asignado:     Optional[int]
    juez_username:       Optional[str]
    combates_pendientes: int


class GafeteResponse(BaseModel):
    """Datos para imprimir el gafete con QR."""
    nombre_alumno:  str
    foto:           Optional[str]
    edad:           int
    escuela:        str
    categoria:      str
    torneo:         str
    fecha_torneo:   str
    sede:           str
    token_qr:       str
    idinscripcion:  int


class EscaneoQRResponse(BaseModel):
    ok:                 bool
    valido:             bool
    en_area_correcta:   Optional[bool]
    nombre_alumno:      Optional[str]
    foto:               Optional[str]
    escuela:            Optional[str]
    cinta:              Optional[str]
    color_cinta:        Optional[str]
    idinscripcion:      Optional[int]
    tipo_torneo:        Optional[str]
    num_combates_realizados: Optional[int]
    max_combates:       Optional[int]
    mensaje:            str
    area_correcta:      Optional[str]
    area_escaneada:     Optional[str]


class AlumnoElegibleResponse(BaseModel):
    idalumno:        int
    nombres:         str
    apellidopaterno: str
    edad:            int
    cinta:           str
    color_cinta:     str
    peso:            Optional[float]
    genero:          Optional[str]
    ya_inscrito:     bool


class InscripcionResponse(BaseModel):
    idinscripcion:    int
    idalumno:         int
    nombre_alumno:    str
    cinta:            str
    edad:             int
    peso:             Optional[float]
    genero:           Optional[str]
    estatus_pago:     str
    qr_generado:      bool
    qr_usado:         bool
    lugar_obtenido:   Optional[int]
    fecha_inscripcion: str


class MatchResponse(BaseModel):
    categoria:       str
    participantes:   list[dict]
    enfrentamientos: list[dict]