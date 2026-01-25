from fastapi import FastAPI
# Importamos los routers de cada módulo
from app.routers.auth import router as auth_router
from app.routers.usuarios import router as usuarios_router
from app.routers.alumnos import router as alumnos_router
from app.routers.profesores import router as profesores_router
from app.routers.catalogos import router as catalogos_router
from app.routers.torneos import router as torneos_router

app = FastAPI(
    title="Taekwondo Management & Tournament System",
    description="API modular para la gestión integral de escuelas de Taekwondo y organización de torneos con brackets en vivo.",
    version="2.1.0"
)

# --- REGISTRO DE ROUTERS ---

# Autenticación y Login
app.include_router(auth_router)

# Gestión de Usuarios y Roles (SuperAdmin, Escuela, Profesor, Juez)
app.include_router(usuarios_router)

# Gestión de Alumnos e Información Médica
app.include_router(alumnos_router)

# Gestión de Profesores y Staff
app.include_router(profesores_router)

# Módulo de Torneos, Categorías y Brackets
app.include_router(torneos_router)

# Catálogos (Cintas, Grados, etc.)
app.include_router(catalogos_router)


# --- RUTAS GENERALES ---

@app.get("/", tags=["General"])
def root():
    """Ruta de bienvenida y verificación de estado."""
    return {
        "app": "Taekwondo System API",
        "version": "2.1.0",
        "status": "Online",
        "docs": "/docs"
    }