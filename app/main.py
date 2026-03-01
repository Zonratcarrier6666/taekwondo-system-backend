import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configuración del path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Importación de routers
from routers import (
    auth,
    usuarios,
    alumnos,
    torneos,
    profesores,
    escuelas,
    cintagrados,
    examen,
    pagos,
    mensualidades,
    test_correos,
    dashboard,
    asistencia,
    asistencia_torneo,
    brackets,
)

# Scheduler
from utils.scheduler import start_scheduler, stop_scheduler, revisar_pagos_y_notificar

tags_metadata = [
    {"name": "Autenticación",               "description": "Acceso al sistema y gestión de tokens JWT."},
    {"name": "Estadísticas y Dashboard",    "description": "Métricas financieras y operativas para Escuelas y Profesores."},
    {"name": "Asistencia y Control",        "description": "Gestión de presencia diaria de alumnos."},
    {"name": "Administración del Sistema",  "description": "Registro de Escuelas, Profesores y Jueces."},
    {"name": "Gestión Escolar",             "description": "Mantenimiento de Alumnos, Profesores y Perfiles de Escuela."},
    {"name": "Exámenes y Grados",           "description": "Control de eventos de promoción y avance técnico."},
    {"name": "Finanzas y Cobranza",         "description": "Caja, mensualidades masivas y recibos."},
    {"name": "Torneos y Competencias",      "description": "Logística, categorías, inscripciones y validación QR."},
    {"name": "Mantenimiento y Debug",       "description": "Utilidades de prueba para desarrollo."},
]


# ─── Lifespan: startup y shutdown ────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()         # ← arranca el cron al iniciar uvicorn
    yield
    stop_scheduler()          # ← lo detiene limpiamente al cerrar


# ─── App ─────────────────────────────────────────────────────
app = FastAPI(
    title="TKW System API",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers normales ────────────────────────────────────────
# 1. Autenticación
app.include_router(auth.router,          prefix="/auth",          tags=["Autenticación"])
# 2. Análisis
app.include_router(dashboard.router,     prefix="/dashboard",     tags=["Estadísticas y Dashboard"])
app.include_router(asistencia.router,    prefix="/asistencia",    tags=["Asistencia y Control"])
# 3. Estructura y Jerarquía
app.include_router(usuarios.router,      prefix="/usuarios",      tags=["Administración del Sistema"])
# 4. Operación Diaria
app.include_router(alumnos.router,       prefix="/alumnos",       tags=["Gestión Escolar"])
app.include_router(profesores.router,    prefix="/profesores",    tags=["Gestión Escolar"])
app.include_router(escuelas.router,      prefix="/escuelas",      tags=["Gestión Escolar"])
# 5. Evolución Técnica
app.include_router(cintagrados.router,   prefix="/grados",        tags=["Exámenes y Grados"])
app.include_router(examen.router,        prefix="/examenes",      tags=["Exámenes y Grados"])
# 6. Módulo Financiero
app.include_router(pagos.router,         prefix="/finanzas",      tags=["Finanzas y Cobranza"])
app.include_router(mensualidades.router, prefix="/mensualidades", tags=["Finanzas y Cobranza"])
# 7. Torneos
app.include_router(torneos.router,       prefix="/torneos",       tags=["Torneos y Competencias"])
app.include_router(asistencia.router,    prefix="/asistencia-torneo", tags=["Torneos y Competencias"])
# 8. Brackets y combates
app.include_router(brackets.router,      tags=["Torneos y Competencias"])

# 9. Pruebas
app.include_router(test_correos.router,  prefix="/debug",         tags=["Mantenimiento y Debug"])

# ─── Endpoint para forzar el scheduler manualmente ───────────
# Útil para probar sin esperar las 9 AM
from fastapi import APIRouter
_router_admin = APIRouter(prefix="/admin", tags=["Mantenimiento y Debug"])

@_router_admin.post(
    "/scheduler/ejecutar-ahora",
    summary="Forzar revisión de pagos ahora (solo pruebas)"
)
async def ejecutar_scheduler_ahora():
    await revisar_pagos_y_notificar()
    return {"ok": True, "mensaje": "Revisión ejecutada. Revisa la consola del servidor."}

app.include_router(_router_admin)