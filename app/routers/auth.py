from fastapi import APIRouter, HTTPException
from app.database import supabase
from app.schemas import RegistroEscuelaMaestro

router = APIRouter(prefix="/auth", tags=["Autenticación"])

@router.post("/registrar-escuela")
async def registro_maestro(datos: RegistroEscuelaMaestro):
    """Proceso de alta para SuperAdmin: Crea Usuario, Escuela y Profesor de un jalón."""
    try:
        # 1. Crear Usuario (Rol Escuela por defecto para el dueño)
        user_insert = {
            "username": datos.username,
            "passwordhash": datos.password, # TODO: Aplicar hashing en el futuro
            "rol": "Escuela"
        }
        res_user = supabase.table("usuarios").insert(user_insert).execute()
        if not res_user.data:
            raise HTTPException(status_code=400, detail="Error al crear cuenta de usuario")
        
        user_id = res_user.data[0]["idusuario"]

        # 2. Crear Escuela ligada al Usuario
        escuela_insert = {
            "idusuario": user_id,
            "nombreescuela": datos.nombre_escuela,
            "direccion": datos.direccion
        }
        res_escuela = supabase.table("datosescuela").insert(escuela_insert).execute()
        escuela_id = res_escuela.data[0]["idescuela"]

        # 3. Crear Profesor (El dueño) ligado a la Escuela
        profesor_insert = {
            "nombrecompleto": datos.nombre_completo_profesor,
            "idgradodan": datos.id_grado_dan,
            "idescuela": escuela_id,
            "estatus": 1
        }
        supabase.table("profesores").insert(profesor_insert).execute()

        return {
            "status": "success",
            "message": "Registro completo exitoso",
            "id_escuela": escuela_id
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en el flujo de registro: {str(e)}")