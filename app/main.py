import sys
import os

# Agrega el directorio actual (/app) al path de Python
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importación de routers
from routers import auth, usuarios, alumnos, torneos, profesores, escuelas, cintagrados, examen, pagos, mensualidades, test_correos
# --- CONFIGURACIÓN DE METADATOS (SWAGGER) ---
tags_metadata = [
    {
        "name": "Autenticación",
        "description": "Acceso al sistema mediante tokens JWT. **Indispensable para obtener el rol del usuario.**",
    },
    {
        "name": "Administración del Sistema",
        "description": "Gestión de usuarios de alto nivel (SuperAdmin), escuelas y jueces.",
    },
    {
        "name": "Gestión Escolar",
        "description": "Operaciones diarias: registro de alumnos, administración de profesores y perfiles de escuela.",
    },
    {
        "name": "Exámenes y Grados",
        "description": "Control de eventos de promoción, historial de cintas y evaluación técnica.",
    },
    {
        "name": "Finanzas y Cobranza",
        "description": "Gestión de ingresos, mensualidades masivas, inscripciones a eventos y estados de cuenta.",
    },
    {
        "name": "Torneos y Competencias",
        "description": "Logística de eventos nacionales, categorías, inscripciones y validación de acceso (QR).",
    },
    {
        "name": "Mantenimiento y Debug",
        "description": "Herramientas de prueba para desarrolladores, como el envío de correos electrónicos de prueba.",
    },
]

# --- INICIALIZACIÓN DE LA APP ---
app = FastAPI(
    title="Taekwondo Management System API",
    description="""
    ## 🥋 Plataforma de Gestión Integral para Academias de Taekwondo
    
    Esta API centraliza la operación administrativa, financiera y deportiva de las escuelas vinculadas.
    
    ### 🚀 Características Principales:
    * **Seguridad Jerárquica**: Acceso basado en roles (SuperAdmin, Escuela, Profesor, Juez).
    * **Lógica Predictiva**: El sistema identifica automáticamente tu escuela y profesor mediante el token JWT.
    * **Automatización Financiera**: Generación masiva de mensualidades y cargos automáticos por inscripción a torneos.
    * **Logística de Torneos**: Creación de categorías, control de pesaje y validación de acceso mediante QR activado por pago.
    
    ### 🔐 Autorización:
    Utiliza el botón **Authorize** arriba a la derecha para ingresar tu token `Bearer`. 
    _Nota: Los permisos varían según el rol del usuario logueado._
    """,
    version="1.5.0",
    openapi_tags=tags_metadata,
    contact={
        "name": "Soporte Técnico TKD System",
        "url": "https://tkdsystem.com/soporte",
        "email": "soporte@tkdsystem.com",
    },
    license_info={
        "name": "Propiedad Privada - TKD System 2026",
    },
)

# --- MIDDLEWARE (CORS) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REGISTRO DE ROUTERS ---

# Autenticación
app.include_router(auth.router, prefix="/auth", tags=["Autenticación"])

# Administración y Usuarios
app.include_router(usuarios.router, prefix="/usuarios", tags=["Administración del Sistema"])

# Gestión Escolar
app.include_router(alumnos.router, prefix="/alumnos", tags=["Gestión Escolar"])
app.include_router(profesores.router, prefix="/profesores", tags=["Gestión Escolar"])
app.include_router(escuelas.router, prefix="/escuelas", tags=["Gestión Escolar"])

# Grados y Exámenes
app.include_router(cintagrados.router, prefix="/grados", tags=["Exámenes y Grados"])
app.include_router(examen.router, prefix="/examenes", tags=["Exámenes y Grados"])

# Finanzas y Pagos
app.include_router(pagos.router, prefix="/finanzas", tags=["Finanzas y Cobranza"])
app.include_router(mensualidades.router, prefix="/mensualidades", tags=["Finanzas y Cobranza"])

# Torneos
app.include_router(torneos.router, prefix="/torneos", tags=["Torneos y Competencias"])

# Utilidades de Debug
app.include_router(test_correos.router, prefix="/debug", tags=["Mantenimiento y Debug"])

# --- ENDPOINTS GENERALES ---
@app.get("/", tags=["General"], summary="Verificar estado de la API")
async def root():
    """Retorna un mensaje simple para verificar que el servicio está en línea."""
    return {
        "status": "online",
        "api_name": "Taekwondo Management System",
        "version": "1.5.0"
    }