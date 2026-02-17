from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.dashboard import AsistenciaRegistro

router = APIRouter(prefix="/asistencia", tags=["Asistencia y Control"])

@router.post("/registrar")
async def registrar_asistencia(
    datos: AsistenciaRegistro,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    id_usuario = user.get("idusuario")
    rol = user.get("rol")
    
    id_escuela = None
    if rol == "Escuela":
        res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if res.data: id_escuela = res.data[0]["idescuela"]
    elif rol == "Profesor":
        res = db.table("profesores").select("idescuela").eq("idusuario", id_usuario).execute()
        if res.data: id_escuela = res.data[0]["idescuela"]

    if not id_escuela:
        raise HTTPException(status_code=403, detail="No tienes una escuela asignada para registrar asistencia.")

    payload = {
        "idalumno": datos.idalumno,
        "fecha": datos.fecha,
        "presente": datos.presente,
        "idescuela": id_escuela
    }
    
    try:
        res = db.table("asistencia").upsert(payload, on_conflict="idalumno,fecha").execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al registrar asistencia: {str(e)}")