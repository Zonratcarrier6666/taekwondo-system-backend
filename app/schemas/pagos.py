# ============================================================
#  app/schemas/pagos.py
# ============================================================

from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, Literal
from datetime import date, datetime
from enum import IntEnum, Enum


class TipoPago(IntEnum):
    MENSUALIDAD = 1
    INSCRIPCION = 2
    EXAMEN      = 3
    TORNEO      = 4
    OTRO        = 5

class EstatusPago(IntEnum):
    PENDIENTE  = 0
    PAGADO     = 1
    CANCELADO  = 2
    VENCIDO    = 3

class MetodoPago(str, Enum):
    EFECTIVO      = "Efectivo"
    TRANSFERENCIA = "Transferencia"
    TARJETA       = "Tarjeta"
    OTRO          = "Otro"

class CicloSemestral(str, Enum):
    ENERO_JUNIO     = "ENE-JUN"
    JULIO_DICIEMBRE = "JUL-DIC"


# ─── Helpers de ciclo ────────────────────────────────────────

def get_ciclo_actual(fecha: date = None) -> CicloSemestral:
    f = fecha or date.today()
    return CicloSemestral.ENERO_JUNIO if f.month <= 6 else CicloSemestral.JULIO_DICIEMBRE

def alumno_debe_inscripcion(fecha_registro: date, fecha_hoy: date = None) -> bool:
    """
    Devuelve True si al alumno ya se le puede cobrar inscripción.
    Regla: no se cobra en el mismo ciclo semestral de su registro.
    """
    hoy = fecha_hoy or date.today()
    ciclo_reg = get_ciclo_actual(fecha_registro)
    ciclo_hoy = get_ciclo_actual(hoy)
    if ciclo_reg == ciclo_hoy and fecha_registro.year == hoy.year:
        return False
    return True


# ─── Crear pagos ────────────────────────────────────────────

class CrearPagoMensualidad(BaseModel):
    idalumno:            int
    monto:               float
    mes_correspondiente: str          # "2024-11"
    metodo_pago:         Optional[MetodoPago] = None
    notas_adicionales:   Optional[str] = None

    @field_validator("monto")
    @classmethod
    def monto_pos(cls, v):
        if v <= 0: raise ValueError("Monto debe ser > 0")
        return v

    @field_validator("mes_correspondiente")
    @classmethod
    def fmt_mes(cls, v):
        try: datetime.strptime(v, "%Y-%m")
        except: raise ValueError("Formato: YYYY-MM")
        return v


class CrearPagoInscripcion(BaseModel):
    idalumno:          int
    monto:             float
    ciclo:             CicloSemestral
    year:              int
    notas_adicionales: Optional[str] = None

    @field_validator("monto")
    @classmethod
    def monto_pos(cls, v):
        if v <= 0: raise ValueError("Monto debe ser > 0")
        return v


class GenerarPagosMasivosMensualidad(BaseModel):
    idescuela:               int
    mes_correspondiente:     str
    monto_default:           float
    dia_cobro_default:       int = 1
    sobrescribir_existentes: bool = False

    @field_validator("dia_cobro_default")
    @classmethod
    def dia_val(cls, v):
        if not 1 <= v <= 28: raise ValueError("Día entre 1 y 28")
        return v


class GenerarInscripcionesSemestrales(BaseModel):
    idescuela:               int
    ciclo:                   CicloSemestral
    year:                    int
    monto:                   float
    sobrescribir_existentes: bool = False


# ─── Cobrar ──────────────────────────────────────────────────

class RegistrarPago(BaseModel):
    idpago:          int
    metodo_pago:     MetodoPago
    url_comprobante: Optional[str] = None
    notas:           Optional[str] = None


class RegistrarPagoLote(BaseModel):
    idpagos:     list[int]
    metodo_pago: MetodoPago
    notas:       Optional[str] = None


# ─── Config por alumno ───────────────────────────────────────

class ConfigPagoAlumno(BaseModel):
    idalumno:          int
    monto_mensualidad: float
    dia_cobro:         int
    monto_inscripcion: Optional[float] = None

    @field_validator("dia_cobro")
    @classmethod
    def dia_val(cls, v):
        if not 1 <= v <= 28: raise ValueError("Día entre 1 y 28")
        return v


class ConfigPagoAlumnoLote(BaseModel):
    configs: list[ConfigPagoAlumno]


# ─── Formulario tutor ────────────────────────────────────────

class FormularioTutor(BaseModel):
    # Tutor
    nombre_tutor:    str
    curp_tutor:      Optional[str] = None
    direccion_tutor: str
    correo_tutor:    Optional[str] = None
    telefono_tutor:  Optional[str] = None

    # Alumno
    nombre_alumno:   str
    curp_alumno:     Optional[str] = None
    fecha_nacimiento: str

    # Médicos
    tipo_sangre:     Optional[str] = None
    alergias:        str = "Ninguna"
    padecimientos:   str = "Ninguno"
    seguro_medico:   Optional[str] = None
    contacto_emergencia_nombre: Optional[str] = None
    contacto_emergencia_tel:    Optional[str] = None

    # Autorizaciones
    acepta_reglamento:   bool
    autoriza_uso_imagen: bool
    firma_url:           Optional[str] = None

    # Referencia
    idalumno:  int
    idescuela: int
    ciclo:     CicloSemestral
    year:      int

    @model_validator(mode="after")
    def check_contacto(self):
        if not self.correo_tutor and not self.telefono_tutor:
            raise ValueError("Proporciona correo o teléfono del tutor")
        return self

    @field_validator("acepta_reglamento")
    @classmethod
    def debe_aceptar(cls, v):
        if not v: raise ValueError("El tutor debe aceptar el reglamento")
        return v


class SubirFormularioFirmado(BaseModel):
    idalumno:  int
    idpago:    int
    firma_url: str
    notas:     Optional[str] = None


class ValidarFormulario(BaseModel):
    idalumno:       int
    idpago:         int
    aprobado:       bool
    motivo_rechazo: Optional[str] = None


# ─── Notificaciones ──────────────────────────────────────────

class EnviarNotificacion(BaseModel):
    idalumno:     int
    tipo:         Literal["pago_pendiente", "inscripcion", "formulario", "recordatorio"]
    idpago:       Optional[int] = None
    mensaje_extra: Optional[str] = None


class EnviarNotificacionLote(BaseModel):
    idalumnos: list[int]
    tipo:      Literal["pago_pendiente", "inscripcion", "formulario", "recordatorio"]


# ─── Responses ───────────────────────────────────────────────

class ResumenPagosAlumno(BaseModel):
    idalumno:                 int
    nombres:                  str
    apellidopaterno:          str
    mensualidades_pagadas:    int
    mensualidades_pendientes: int
    inscripcion_ciclo_actual: Optional[str] = None
    formulario_status:        Optional[str] = None
    total_adeudo:             float
    dia_cobro:                int
    monto_mensualidad:        float


class NotificacionResult(BaseModel):
    idalumno:  int
    email_ok:  Optional[bool] = None
    error:     Optional[str]  = None