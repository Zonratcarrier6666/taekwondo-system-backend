from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from typing import List, Optional
from datetime import datetime
from supabase import Client
import uuid

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.pagos import Pago, ProcesoPago, EstatusPago
from app.schemas.usuarios import UserRole

# Eliminamos el prefix aquí para evitar la URL duplicada /finanzas/finanzas
router = APIRouter(tags=["Finanzas y Pagos"])

@router.get("/", response_model=List[Pago])
async def listar_todos_los_pagos(
    estatus: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Lista todos los pagos de la escuela (pagados y pendientes).
    Corregido: Se cambió el filtro 'status' por 'estatus' para coincidir con la BD.
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
        raise HTTPException(status_code=404, detail="Escuela no identificada para este usuario.")

    # JOIN con alumnos para traer nombres
    # Importante: el nombre de la columna en el filtro .eq() DEBE ser 'estatus'
    query = db.table("pagos").select("*, alumno:alumnos(nombres, apellidopaterno, apellidomaterno)").eq("idescuela", id_escuela)
    
    if estatus is not None:
        query = query.eq("estatus", estatus) # FIX: Antes decía "status"
    
    try:
        result = query.order("fecharegistro", desc=True).execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en consulta de base de datos: {str(e)}")

@router.get("/{idpago}", response_model=Pago)
async def obtener_detalle_pago(
    idpago: int,
    db: Client = Depends(get_db)
):
    """Obtiene el detalle de un pago específico y el alumno relacionado."""
    result = db.table("pagos").select("*, alumno:alumnos(nombres, apellidopaterno, apellidomaterno)").eq("idpago", idpago).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Pago no encontrado.")
    return result.data[0]

@router.get("/{idpago}/recibo-impresion", response_model=dict)
async def obtener_datos_recibo_impresion(
    idpago: int,
    db: Client = Depends(get_db)
):
    """Consolida datos de Escuela, Alumno y Pago para el Canvas de impresión."""
    pago_res = db.table("pagos").select(
        "*, alumno:alumnos(*, grado:cintasgrados(*))"
    ).eq("idpago", idpago).execute()
    
    if not pago_res.data:
        raise HTTPException(status_code=404, detail="Pago no encontrado.")
    
    pago_info = pago_res.data[0]
    id_escuela = pago_info["idescuela"]

    escuela_res = db.table("datosescuela").select("*").eq("idescuela", id_escuela).execute()
    escuela_info = escuela_res.data[0] if escuela_res.data else {}

    return {
        "metadata": {
            "folio": pago_info.get("folio_recibo", "S/F"),
            "fecha_impresion": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "estatus_texto": "PAGADO" if pago_info["estatus"] == 1 else "PENDIENTE"
        },
        "escuela": {
            "nombre": escuela_info.get("nombreescuela", "Academia de Taekwondo"),
            "lema": escuela_info.get("lema", ""),
            "direccion": escuela_info.get("direccion", ""),
            "telefono": escuela_info.get("telefono_oficina", ""),
            "logo_url": escuela_info.get("logo_url", "")
        },
        "alumno": {
            "nombre_completo": f"{pago_info['alumno']['nombres']} {pago_info['alumno']['apellidopaterno']}",
            "grado_actual": pago_info["alumno"]["grado"]["color"] if pago_info["alumno"].get("grado") else "N/A",
            "id_interno": pago_info["idalumno"]
        },
        "pago": {
            "monto": pago_info["monto"],
            "concepto": pago_info["concepto"],
            "metodo": pago_info.get("metodo_pago", "No registrado"),
            "fecha_pago": pago_info["fecha_pago"],
            "notas": pago_info.get("notas_adicionales", ""),
            "desglose": pago_info.get("desglose_interno", [])
        }
    }

@router.post("/comprobante/{idpago}", response_model=Pago)
async def subir_comprobante_pago(
    idpago: int,
    file: UploadFile = File(...),
    db: Client = Depends(get_db)
):
    """Sube el comprobante al Storage y actualiza url_comprobante."""
    extension = file.filename.split(".")[-1].lower()
    if extension not in ["jpg", "jpeg", "png", "pdf"]:
        raise HTTPException(status_code=400, detail="Formato no soportado.")

    file_path = f"comprobantes/pago_{idpago}_{uuid.uuid4()}.{extension}"
    file_content = await file.read()

    try:
        db.storage.from_("alumnos").upload(path=file_path, file=file_content)
        url_publica = db.storage.from_("alumnos").get_public_url(file_path)
        result = db.table("pagos").update({"url_comprobante": url_publica}).eq("idpago", idpago).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en Storage: {str(e)}")

@router.post("/cobrar/{idpago}", response_model=Pago)
async def registrar_cobro_completo(
    idpago: int,
    datos: ProcesoPago,
    db: Client = Depends(get_db)
):
    """Registra el cobro y genera folio de recibo."""
    pago_res = db.table("pagos").select("monto, estatus").eq("idpago", idpago).execute()
    if not pago_res.data:
        raise HTTPException(status_code=404, detail="Pago no encontrado.")
    
    if pago_res.data[0]["estatus"] == EstatusPago.PAGADO.value:
        raise HTTPException(status_code=400, detail="Este pago ya fue liquidado.")

    monto_deuda = float(pago_res.data[0]["monto"])
    if abs(datos.monto_total_recibido - monto_deuda) > 0.01:
        raise HTTPException(status_code=400, detail=f"Monto incorrecto. Deuda: ${monto_deuda}")

    folio = f"REC-{datetime.now().year}-{str(uuid.uuid4())[:8].upper()}"
    
    update_payload = {
        "estatus": EstatusPago.PAGADO.value,
        "metodo_pago": datos.resumen_metodos,
        "fecha_pago": datetime.now().isoformat(),
        "folio_recibo": folio,
        "notas_adicionales": datos.notas,
        "desglose_interno": [d.model_dump() for d in datos.desglose_pagos]
    }

    result = db.table("pagos").update(update_payload).eq("idpago", idpago).execute()
    return result.data[0]