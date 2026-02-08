from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from datetime import date
from supabase import Client

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.cintagrados import Cinta, PromocionAlumno, HistorialGrado
from app.schemas.usuarios import UserRole

# Sin prefix porque ya se define en main.py
router = APIRouter()

@router.get("/", response_model=List[Cinta])
async def listar_grados(db: Client = Depends(get_db)):
    """Retorna el catálogo de cintas."""
    try:
        result = db.table("cintasgrados").select("*").order("idgrado").execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/promocionar/{idalumno}", status_code=status.HTTP_200_OK)
async def promocionar_alumno(
    idalumno: int,
    datos: PromocionAlumno,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Registra un ascenso de grado y actualiza al alumno."""
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")
    
    if rol not in [UserRole.ESCUELA, UserRole.PROFESOR]:
        raise HTTPException(status_code=403, detail="No tienes permisos.")

    # 1. Obtener alumno y validar pertenencia
    alumno_res = db.table("alumnos").select("idalumno, idescuela, idprofesor, idgradoactual").eq("idalumno", idalumno).execute()
    if not alumno_res.data:
        raise HTTPException(status_code=404, detail="Alumno no encontrado.")
    
    alumno = alumno_res.data[0]
    id_grado_anterior = alumno["idgradoactual"]

    # 2. Identificar evaluador
    id_evaluador = None
    if rol == UserRole.PROFESOR:
        profe = db.table("profesores").select("idprofesor").eq("idusuario", id_usuario).execute()
        if not profe.data or profe.data[0]["idprofesor"] != alumno["idprofesor"]:
            raise HTTPException(status_code=403, detail="No tienes permiso sobre este alumno.")
        id_evaluador = profe.data[0]["idprofesor"]
    else:
        escuela = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if not escuela.data or escuela.data[0]["idescuela"] != alumno["idescuela"]:
            raise HTTPException(status_code=403, detail="Este alumno no pertenece a tu escuela.")

    # 3. Guardar historial y actualizar alumno
    try:
        # Registro en historial
        db.table("historial_grados").insert({
            "idalumno": idalumno,
            "idgrado_anterior": id_grado_anterior,
            "idgrado_nuevo": datos.id_nuevo_grado,
            "fecha_examen": str(datos.fecha_examen),
            "idprofesor_evaluador": id_evaluador,
            "notas": datos.notas
        }).execute()
        
        # Actualización de alumno
        db.table("alumnos").update({"idgradoactual": datos.id_nuevo_grado}).eq("idalumno", idalumno).execute()
        
        return {"message": "Promoción exitosa", "nuevo_grado": datos.id_nuevo_grado}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en base de datos: {str(e)}")

@router.get("/historial/{idalumno}", response_model=List[HistorialGrado])
async def obtener_historial(idalumno: int, db: Client = Depends(get_db)):
    """Historial de cintas del alumno con nombres de colores."""
    try:
        result = db.table("historial_grados")\
            .select("*, grado_anterior:cintasgrados!idgrado_anterior(*), grado_nuevo:cintasgrados!idgrado_nuevo(*)")\
            .eq("idalumno", idalumno)\
            .order("fecharegistro", desc=True)\
            .execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))