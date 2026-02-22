import sys
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Configuración del path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Importación de routers (Asegúrate de que los archivos existan)
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
    asistencia
)

tags_metadata = [
    {"name": "Autenticación", "description": "Acceso al sistema y gestión de tokens JWT."},
    {"name": "Estadísticas y Dashboard", "description": "Métricas financieras y operativas para Escuelas y Profesores."},
    {"name": "Asistencia y Control", "description": "Gestión de presencia diaria de alumnos."},
    {"name": "Administración del Sistema", "description": "Registro de Escuelas, Profesores y Jueces."},
    {"name": "Gestión Escolar", "description": "Mantenimiento de Alumnos, Profesores y Perfiles de Escuela."},
    {"name": "Exámenes y Grados", "description": "Control de eventos de promoción y avance técnico."},
    {"name": "Finanzas y Cobranza", "description": "Caja, mensualidades masivas y recibos."},
    {"name": "Torneos y Competencias", "description": "Logística, categorías, inscripciones y validación QR."},
    {"name": "Mantenimiento y Debug", "description": "Utilidades de prueba para desarrollo."},
]

app = FastAPI(
    title="Taekwondo Management System API",
    description="Backend centralizado para la gestión de escuelas de artes marciales.",
    version="1.5.0",
    openapi_tags=tags_metadata
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MAPEO LÓGICO DE ROUTERS ---

# 1. Autenticación (Público/General)
app.include_router(auth.router, prefix="/auth", tags=["Autenticación"])

# 2. Análisis (Escuela / Profesor)
app.include_router(dashboard.router, prefix="/dashboard", tags=["Estadísticas y Dashboard"])
app.include_router(asistencia.router, prefix="/asistencia", tags=["Asistencia y Control"])

# 3. Estructura y Jerarquía (SuperAdmin / Escuela)
app.include_router(usuarios.router, prefix="/usuarios", tags=["Administración del Sistema"])

# 4. Operación Diaria (Escuela / Profesor)
app.include_router(alumnos.router, prefix="/alumnos", tags=["Gestión Escolar"])
app.include_router(profesores.router, prefix="/profesores", tags=["Gestión Escolar"])
app.include_router(escuelas.router, prefix="/escuelas", tags=["Gestión Escolar"])

# 5. Evolución Técnica (Escuela / Profesor)
app.include_router(cintagrados.router, prefix="/grados", tags=["Exámenes y Grados"])
app.include_router(examen.router, prefix="/examenes", tags=["Exámenes y Grados"])

# 6. Módulo Financiero (Escuela)
app.include_router(pagos.router, prefix="/finanzas", tags=["Finanzas y Cobranza"])
app.include_router(mensualidades.router, prefix="/mensualidades", tags=["Finanzas y Cobranza"])

# 7. Eventos Nacionales (Todos / Juez para Validar QR)
app.include_router(torneos.router, prefix="/torneos", tags=["Torneos y Competencias"])

# 8. Pruebas
app.include_router(test_correos.router, prefix="/debug", tags=["Mantenimiento y Debug"])

@app.get("/", tags=["General"])
async def root():
    return {"status": "online", "api_name": "TKD System API", "version": "1.5.0"}