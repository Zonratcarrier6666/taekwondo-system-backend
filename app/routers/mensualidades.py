from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from supabase import Client
from datetime import datetime

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.mensualidades import GenerarMensualidadesBase, ResultadoGeneracion
from app.schemas.usuarios import UserRole
from app.schemas.pagos import TipoPago, EstatusPago

router = APIRouter(prefix="/mensualidades", tags=["Finanzas y Pagos"])

@router.post("/generar-mes", response_model=ResultadoGeneracion)
async def generar_mensualidades_escuela(
    datos: GenerarMensualidadesBase,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Genera cargos masivos de mensualidad.
    Utiliza el 'dia_corte' enviado en el JSON para decidir si un alumno nuevo paga o no.
    """
    id_usuario = current_user.get("idusuario")
    rol = current_user.get("rol")
    
    id_escuela = None
    if rol == UserRole.ESCUELA:
        res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if res.data: id_escuela = res.data[0]["idescuela"]
    elif rol == UserRole.PROFESOR:
        res = db.table("profesores").select("idescuela").eq("idusuario", id_usuario).execute()
        if res.data: id_escuela = res.data[0]["idescuela"]

    if not id_escuela:
        raise HTTPException(status_code=404, detail="Escuela no identificada.")

    # 1. Obtener alumnos activos
    alumnos_res = db.table("alumnos").select("idalumno, fecharegistro").eq("idescuela", id_escuela).execute()
    alumnos = alumnos_res.data

    cargos_creados = 0
    alumnos_omitidos = 0
    monto_acumulado = 0.0
    concepto = f"{datos.concepto_prefijo} {datos.mes}/{datos.anio}"

    for alumno in alumnos:
        # A. Lógica de Cortesía para Alumnos Nuevos
        # Convertimos la fecha de registro de la BD a objeto datetime
        fecha_ingreso = datetime.fromisoformat(alumno["fecharegistro"].replace("Z", "+00:00"))
        
        # Si el alumno se inscribió en el mismo mes/año que estamos procesando
        if fecha_ingreso.month == datos.mes and fecha_ingreso.year == datos.anio:
            # Comparamos contra el dia_corte dinámico que viene en la petición
            if fecha_ingreso.day > datos.dia_corte:
                alumnos_omitidos += 1
                continue

        # B. Evitar Duplicados (Protección contra doble clic)
        check = db.table("pagos").select("idpago")\
            .eq("idalumno", alumno["idalumno"])\
            .eq("id_tipo_pago", TipoPago.MENSUALIDAD.value)\
            .ilike("concepto", f"%{datos.mes}/{datos.anio}%")\
            .execute()
        
        if check.data:
            alumnos_omitidos += 1
            continue

        # C. Inserción del Cargo Pendiente
        try:
            db.table("pagos").insert({
                "idalumno": alumno["idalumno"],
                "idescuela": id_escuela,
                "id_tipo_pago": TipoPago.MENSUALIDAD.value,
                "monto": datos.monto_estandar,
                "concepto": concepto,
                "estatus": EstatusPago.PENDIENTE.value
            }).execute()
            
            cargos_creados += 1
            monto_acumulado += datos.monto_estandar
        except Exception:
            alumnos_omitidos += 1

    return {
        "mes": datos.mes,
        "anio": datos.anio,
        "cargos_creados": cargos_creados,
        "alumnos_omitidos": alumnos_omitidos,
        "total_monto_proyectado": monto_acumulado
    }