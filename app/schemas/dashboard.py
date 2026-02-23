from pydantic import BaseModel
from typing import List, Dict, Optional, Any


# ─────────────────────────────────────────────────────────────
#  COMPARTIDOS
# ─────────────────────────────────────────────────────────────

class BeltStat(BaseModel):
    idgrado: Optional[int] = None
    color: str
    nivelkupdan: Optional[str] = None
    count: int


class FinanceStat(BaseModel):
    label: str          # "Lun", "Mar", etc.
    dia: Optional[str] = None   # "2024-11-11"
    value: float


class FinanceMes(BaseModel):
    mes_label: str      # "Nov", "Dic"
    mes: Optional[str] = None
    total: float


class ExamenProximo(BaseModel):
    idexamen: int
    nombre_examen: str
    fecha_programada: str
    lugar: Optional[str] = None
    costo_examen: Optional[float] = 0.0
    sinodal: Optional[str] = None
    alumnos_inscritos: Optional[int] = 0


class TorneoProximo(BaseModel):
    idtorneo: int
    nombre: str
    fecha: str
    sede: str
    costo_inscripcion: Optional[float] = 0.0
    total_inscritos: Optional[int] = 0


class AlumnoCumple(BaseModel):
    idalumno: int
    nombres: str
    apellidopaterno: str
    fechanacimiento: str
    edad: int
    fecha_display: Optional[str] = None


# ─────────────────────────────────────────────────────────────
#  ESCUELA
# ─────────────────────────────────────────────────────────────

class AlumnoDeudaVencida(BaseModel):
    idalumno: int
    nombres: str
    apellidopaterno: str
    monto: float
    concepto: str
    dias_vencido: int


class AsistenciaDia(BaseModel):
    fecha: str
    label: str
    presentes: int


class DashboardEscuela(BaseModel):
    # Conteos operativos
    total_alumnos_activos: int
    total_alumnos_inactivos: int
    total_profesores: int

    # Finanzas
    ingresos_mes_actual: float
    ingresos_mes_anterior: float
    deuda_total_pendiente: float
    pagos_pendientes_count: int

    # Gráficas financieras
    ingresos_semana: List[FinanceStat]
    ingresos_6_meses: List[FinanceMes]

    # Técnico
    distribucion_cintas: List[BeltStat]

    # Operativo
    alumnos_deuda_vencida: List[AlumnoDeudaVencida]
    proximos_examenes: List[ExamenProximo]
    alumnos_torneo_count: int

    # Asistencia
    asistencia_hoy: int
    asistencia_semana: List[AsistenciaDia]

    # Extra
    alumnos_nuevos_30d: int
    cumpleanos_proximos: List[AlumnoCumple]

    # Compatibilidad hacia atrás (para no romper el frontend actual)
    total_alumnos: Optional[int] = None
    ingresos_semanales: Optional[float] = None
    finanzas_semana: Optional[List[FinanceStat]] = None
    proximos_torneos: Optional[List[dict]] = []


# ─────────────────────────────────────────────────────────────
#  SUPERADMIN
# ─────────────────────────────────────────────────────────────

class EscuelaResumen(BaseModel):
    idescuela: int
    nombreescuela: str
    logo_url: Optional[str] = None
    color_paleta: Optional[str] = None
    alumnos_activos: int
    profesores_activos: int
    ingresos_mes: float
    deuda_pendiente: float
    pagos_pendientes_count: int


class UsuarioItem(BaseModel):
    idusuario: int
    username: str
    rol: str
    fecha_creacion: Optional[str] = None


class EscuelaSimple(BaseModel):
    idescuela: int
    nombreescuela: str
    logo_url: Optional[str] = None


class DashboardSuperAdmin(BaseModel):
    # Conteos globales
    total_escuelas: int
    total_usuarios: int
    total_alumnos_activos: int
    total_profesores_activos: int

    # Finanzas globales
    ingresos_mes_actual: float
    ingresos_mes_anterior: float
    deuda_total_pendiente: float

    # Torneos
    torneos_activos: int
    torneos_proximos_count: int
    total_inscripciones_torneo: int

    # Actividad
    alumnos_nuevos_30d: int
    movimientos_financieros_7d: int

    # Para gráficas
    usuarios_por_rol: Dict[str, int]
    ingresos_ultimos_6_meses: List[FinanceMes]
    escuelas_resumen: List[EscuelaResumen]
    proximos_torneos: List[TorneoProximo]

    # Listas
    usuarios_lista: List[UsuarioItem]
    escuelas: List[EscuelaSimple]

    # Meta
    filtro_aplicado: Optional[int] = None
    resumen_sistema: Dict[str, Any]

    # Compatibilidad hacia atrás
    usuarios_online_recientes: Optional[int] = 0


# ─────────────────────────────────────────────────────────────
#  PROFESOR
# ─────────────────────────────────────────────────────────────

class AlumnoAusente(BaseModel):
    idalumno: int
    nombres: str
    apellidopaterno: str
    fotoalumno: Optional[str] = None
    ultima_asistencia: Optional[str] = None
    dias_ausente: Optional[int] = None


class PromocionGrado(BaseModel):
    idhistorial: int
    nombres: str
    apellidopaterno: str
    grado_anterior: str
    grado_nuevo: str
    nivelkupdan: str
    fecha_examen: str


class AlumnoLista(BaseModel):
    idalumno: int
    nombres: str
    apellidopaterno: str
    fotoalumno: Optional[str] = None
    fechanacimiento: Optional[str] = None
    cinta_color: str
    cinta_nivel: str
    ultima_asistencia: Optional[str] = None
    pagos_pendientes: int


class DashboardProfesor(BaseModel):
    # Mis alumnos
    mis_alumnos_activos: int
    mis_alumnos_inactivos: int

    # Asistencia
    mis_asistencias_hoy: int
    asistencia_semana: List[AsistenciaDia]

    # Técnico
    distribucion_cintas: List[BeltStat]

    # Finanzas (sus alumnos)
    mis_pagos_pendientes_count: int
    mis_pagos_pendientes_monto: float

    # Eventos
    proximos_examenes: List[ExamenProximo]
    mis_alumnos_torneo_count: int

    # Alertas
    alumnos_ausentes: List[AlumnoAusente]
    cumpleanos_proximos: List[AlumnoCumple]
    ultimas_promociones: List[PromocionGrado]

    # Lista completa
    mis_alumnos_lista: List[AlumnoLista]

    # Compatibilidad hacia atrás
    total_alumnos: Optional[int] = None
    distribucion_cintas_porcentaje: Optional[Dict[str, float]] = None
    mensualidades_stats: Optional[Dict[str, int]] = None
    alumnos_en_torneo: Optional[int] = None
    asistencia_reciente: Optional[List[Any]] = []


# ─────────────────────────────────────────────────────────────
#  ASISTENCIA (sin cambios)
# ─────────────────────────────────────────────────────────────

class AsistenciaRegistro(BaseModel):
    idalumno: int
    fecha: str
    presente: bool