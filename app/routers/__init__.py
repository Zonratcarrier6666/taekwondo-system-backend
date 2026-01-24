# Este archivo centraliza los routers para que main.py los vea fácilmente
from .auth import router as auth_router
from .alumnos import router as alumnos_router
from .catalogos import router as catalogos_router
from .profesores import router as profesores_router