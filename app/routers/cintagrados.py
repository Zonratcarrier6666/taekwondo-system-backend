from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from supabase import Client

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.cintagrados import Cinta, HistorialGrado
from app.schemas.examen import PromocionManual
from app.schemas.usuarios import UserRole
from app.schemas.pagos import TipoPago, EstatusPago

router = APIRouter(tags=["Cintas y Grados"])

@router.get("/", response_model=List[Cinta])
async def listar_catalogo_cintas(db: Client = Depends(get_db)):
    """Retorna el catálogo completo de cintas kup/dan."""
    try:
        result = db.table("cintasgrados").select("*").order("idgrado").execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/promocionar-manual", status_code=status.HTTP_200_OK)
async def promocionar_alumno_individual(
    datos: PromocionManual,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Registra una promoción individual (manual) fuera de un evento de examen.
    Si se incluye un 'monto' > 0, genera automáticamente un cargo en la tabla de pagos.
    """
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")
    
    if rol not in [UserRole.ESCUELA, UserRole.PROFESOR]:
        raise HTTPException(status_code=403, detail="No tienes permisos para realizar promociones.")

    # 1. Obtener datos del alumno y validar pertenencia
    alumno_res = db.table("alumnos").select("idalumno, idescuela, idprofesor, idgradoactual").eq("idalumno", datos.idalumno).execute()
    if not alumno_res.data:
        raise HTTPException(status_code=404, detail="Alumno no encontrado.")
    
    alumno = alumno_res.data[0]
    id_grado_anterior = alumno["idgradoactual"]
    id_escuela = alumno["idescuela"]

    if id_grado_anterior == datos.id_nuevo_grado:
        raise HTTPException(status_code=400, detail="El alumno ya posee ese grado.")

    # 2. Identificar evaluador (si es profesor logueado)
    id_evaluador = None
    if rol == UserRole.PROFESOR:
        profe = db.table("profesores").select("idprofesor").eq("idusuario", id_usuario).execute()
        id_evaluador = profe.data[0]["idprofesor"]

    try:
        # 3. Registrar en Historial
        db.table("historial_grados").insert({
            "idalumno": datos.idalumno,
            "idgrado_anterior": id_grado_anterior,
            "idgrado_nuevo": datos.id_nuevo_grado,
            "idexamen": None, # Al ser manual, no hay evento de examen vinculado
            "fecha_examen": str(datos.fecha_promocion),
            "idprofesor_evaluador": id_evaluador,
            "notas": datos.notas
        }).execute()

        # 4. Actualizar grado actual del Alumno
        db.table("alumnos").update({"idgradoactual": datos.id_nuevo_grado}).eq("idalumno", datos.idalumno).execute()

        # 5. GENERAR CARGO FINANCIERO (Si aplica)
        pago_creado = False
        if datos.monto > 0:
            pago_payload = {
                "idalumno": datos.idalumno,
                "idescuela": id_escuela,
                "id_tipo_pago": TipoPago.EXAMEN.value, # Categorizado como trámite de grado
                "monto": datos.monto,
                "concepto": f"Cargo Administrativo: Cambio de Cinta ({datos.notas})",
                "id_referencia_evento": None,
                "estatus": EstatusPago.PENDIENTE.value
            }
            db.table("pagos").insert(pago_payload).execute()
            pago_creado = True

        return {
            "message": "Promoción manual procesada",
            "pago_pendiente_generado": pago_creado,
            "monto": datos.monto if pago_creado else 0
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en el proceso: {str(e)}")

@router.get("/historial/{idalumno}", response_model=List[HistorialGrado])
async def obtener_historial_completo(idalumno: int, db: Client = Depends(get_db)):
    """Obtiene la línea de tiempo de grados del alumno."""
    try:
        result = db.table("historial_grados")\
            .select("*, grado_anterior:cintasgrados!idgrado_anterior(*), grado_nuevo:cintasgrados!idgrado_nuevo(*)")\
            .eq("idalumno", idalumno)\
            .order("fecharegistro", desc=True)\
            .execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))