from fastapi import FastAPI
from app.routers import auth, alumnos, catalogos, profesores

app = FastAPI(
    title="Taekwondo Management System API",
    description="Sistema modular para la gestión de escuelas, alumnos y grados.",
    version="1.1.0"
)

# Inclusión de rutas separadas por módulos
app.include_router(auth.router)
app.include_router(alumnos.router)
app.include_router(catalogos.router)
app.include_router(profesores.router)

@app.get("/", tags=["General"])
def root():
    return {
        "app": "Taekwondo API",
        "status": "Online",
        "docs": "/docs"
    }