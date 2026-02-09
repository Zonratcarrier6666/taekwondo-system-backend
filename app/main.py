from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth, usuarios, alumnos, torneos, profesores, escuelas, cintagrados, examen, pagos, mensualidades,test_correos

# Definición de etiquetas para organizar el orden en Swagger
tags_metadata = [
    {
        "name": "Autenticación",
        "description": "Operaciones de inicio de sesión y obtención de tokens JWT.",
    },
    {
        "name": "Gestión de Usuarios",
        "description": "Administración de cuentas y jerarquía de creación de perfiles.",
    },
    {
        "name": "Gestión de Alumnos",
        "description": "Registro de alumnos con **asignación automática** de Escuela y Profesor según el token.",
    },
    {
        "name": "Gestión de Torneos",
        "description": "Configuración de eventos, categorías e inscripciones.",
    },
]

app = FastAPI(
    title="Taekwondo Management System API",
    description="""
    API robusta para la gestión integral de torneos y escuelas de Taekwondo.
    
    ### Comportamiento Predictivo (Auto-asignación):
    Esta API utiliza el token de seguridad para identificar al usuario y automatizar el flujo de datos:
    * **Registro de Escuela**: Solo el SuperAdmin puede hacerlo.
    * **Registro de Profesor**: El sistema detecta la Escuela del usuario logueado y vincula al profesor automáticamente.
    * **Registro de Alumno**: 
        - Si eres **Profesor**, el sistema detecta tu `idprofesor` y tu `idescuela` y los asigna al alumno.
        - Si eres **Escuela**, el sistema detecta tu `idescuela` y la asigna. Puedes asignar un profesor opcionalmente.
    
    ### Seguridad:
    Utiliza el botón **Authorize** con un token válido para probar los endpoints protegidos.
    """,
    version="1.1.0",
    openapi_tags=tags_metadata,
    contact={
        "name": "Soporte Técnico",
        "email": "soporte@tkdsystem.com",
    },
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusión de Routers
app.include_router(auth.router, prefix="/auth", tags=["Autenticación (Escuelas y Profesores)"])
app.include_router(usuarios.router, prefix="/usuarios", tags=["Gestión de Usuarios (SuperAdmin)"])
app.include_router(alumnos.router, prefix="/alumnos", tags=["Gestión de Alumnos (Profesores y Escuelas)"])
app.include_router(torneos.router, prefix="/torneos", tags=["Gestión de Torneos (Administrador, Escuelas, Profesores y juezes)"])
app.include_router(profesores.router, prefix="/profesores", tags=["Gestión de Profesores (Escuelas)"])
app.include_router(escuelas.router, prefix="/escuelas", tags=["Gestión de la Escuela (Escuelas)"])
app.include_router(cintagrados.router, prefix="/grados", tags=["Cintas y Grados (Profesores y Escuelas)"])
app.include_router(examen.router, prefix="/examenes", tags=["Gestión de Exámenes (Profesores y Escuelas)"])
app.include_router(pagos.router, prefix="/finanzas", tags=["Finanzas y Pagos(Profesores y Escuelas)"])
app.include_router(mensualidades.router, prefix="/mensualidades", tags=["Finanzas y Pagos (Profesores y Escuelas)"])
app.include_router(test_correos.router, prefix="/debug", tags=["Mantenimiento y Debug"])

@app.get("/", tags=["General"])
async def root():
    return {"message": "TKD API is running"}