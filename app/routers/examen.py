from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from supabase import Client
from datetime import date

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.examen import Examen, ExamenCreate, AsignacionExamen, CargaResultadosMasivos
from app.schemas.usuarios import UserRole
from app.schemas.pagos import TipoPago, EstatusPago

router = APIRouter(prefix="/examenes", tags=["Gestión de Exámenes"])

@router.post("/", response_model=Examen, status_code=status.HTTP_201_CREATED)
async def crear_evento_examen(
    datos: ExamenCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Paso 1: Crear el evento con su costo."""
    id_usuario = current_user.get("idusuario")
    rol = current_user.get("rol")
    
    # Obtener idescuela
    if rol == UserRole.ESCUELA:
        res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
    else:
        res = db.table("profesores").select("idescuela").eq("idusuario", id_usuario).execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="Escuela no encontrada.")
    
    id_escuela = res.data[0]["idescuela"]
    payload = datos.model_dump(mode='json')
    payload["idescuela"] = id_escuela

    result = db.table("examenes").insert(payload).execute()
    return result.data[0]

@router.post("/{idexamen}/asignar", status_code=status.HTTP_200_OK)
async def asignar_alumnos_a_examen(
    idexamen: int,
    datos: AsignacionExamen,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Paso 2: Asignar alumnos al examen.
    Esto genera automáticamente los cargos PENDIENTES en la tabla de pagos.
    """
    # 1. Obtener info del examen
    examen = db.table("examenes").select("*").eq("idexamen", idexamen).execute()
    if not examen.data:
        raise HTTPException(status_code=404, detail="Examen no encontrado.")
    
    ex_info = examen.data[0]
    costo = ex_info["costo_examen"]
    id_escuela = ex_info["idescuela"]
    concepto = f"Examen: {ex_info['nombre_examen']}"

    cargos_creados = 0
    for id_alu in datos.alumnos_ids:
        # Evitar duplicar el cargo si ya fue asignado
        existente = db.table("pagos").select("idpago").eq("idalumno", id_alu).eq("id_referencia_evento", idexamen).execute()
        if not existente.data:
            db.table("pagos").insert({
                "idalumno": id_alu,
                "idescuela": id_escuela,
                "id_tipo_pago": TipoPago.EXAMEN.value,
                "monto": costo,
                "concepto": concepto,
                "id_referencia_evento": idexamen,
                "estatus": EstatusPago.PENDIENTE.value
            }).execute()
            cargos_creados += 1

    return {"message": "Alumnos asignados", "cargos_generados": cargos_creados}

@router.post("/{idexamen}/registrar-resultados", status_code=status.HTTP_200_OK)
async def registrar_resultados_finales(
    idexamen: int,
    datos: CargaResultadosMasivos,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Paso 3: Registrar notas y promover.
    CONDICIÓN: Solo permite si el alumno tiene el pago con estatus PAGADO (1).
    """
    id_usuario = current_user.get("idusuario")
    id_evaluador = None
    if current_user.get("rol") == UserRole.PROFESOR:
        profe = db.table("profesores").select("idprofesor").eq("idusuario", id_usuario).execute()
        id_evaluador = profe.data[0]["idprofesor"]

    procesados = []
    bloqueados_por_pago = []

    for res in datos.resultados:
        # Verificar estatus de pago para este examen
        pago_check = db.table("pagos").select("estatus")\
            .eq("idalumno", res.idalumno)\
            .eq("id_referencia_evento", idexamen)\
            .eq("id_tipo_pago", TipoPago.EXAMEN.value)\
            .execute()
        
        # Si no existe pago o no está pagado, se bloquea
        if not pago_check.data or pago_check.data[0]["estatus"] != EstatusPago.PAGADO.value:
            bloqueados_por_pago.append(res.idalumno)
            continue

        # Si pagó, procesamos la promoción
        try:
            alumno = db.table("alumnos").select("idgradoactual").eq("idalumno", res.idalumno).execute()
            grado_ant = alumno.data[0]["idgradoactual"]

            # 1. Historial
            db.table("historial_grados").insert({
                "idalumno": res.idalumno,
                "idgrado_anterior": grado_ant,
                "idgrado_nuevo": res.id_nuevo_grado,
                "idexamen": idexamen,
                "fecha_examen": str(datos.fecha_examen),
                "idprofesor_evaluador": id_evaluador,
                "notas": res.notas
            }).execute()

            # 2. Actualizar grado actual
            db.table("alumnos").update({"idgradoactual": res.id_nuevo_grado}).eq("idalumno", res.idalumno).execute()
            
            procesados.append(res.idalumno)
        except Exception:
            pass

    return {
        "promovidos_exitosamente": procesados,
        "rechazados_por_falta_de_pago": bloqueados_por_pago,
        "total_procesados": len(procesados)
    }