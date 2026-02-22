from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from typing import List
from supabase import Client
import uuid
import os

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.alumnos import Alumno, AlumnoCreate, AlumnoUpdate
from app.schemas.usuarios import UserRole

router = APIRouter()

@router.post("/", response_model=Alumno, status_code=status.HTTP_201_CREATED)
async def registrar_alumno_predictivo(
    alumno: AlumnoCreate, 
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Registra los datos básicos de un alumno.
    Este es el PASO 1. El frontend recibe el objeto creado con su ID,
    y luego decide si subir la foto inmediatamente o dejarlo para después.
    """
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")
    
    if rol not in [UserRole.ESCUELA, UserRole.PROFESOR]:
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar alumnos.")

    id_escuela = None
    id_profesor = None

    if rol == UserRole.PROFESOR:
        profe_data = db.table("profesores").select("idprofesor, idescuela").eq("idusuario", id_usuario).execute()
        if not profe_data.data:
            raise HTTPException(status_code=404, detail="Perfil de profesor no encontrado.")
        id_profesor = profe_data.data[0]["idprofesor"]
        id_escuela = profe_data.data[0]["idescuela"]
        
    elif rol == UserRole.ESCUELA:
        escuela_data = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if not escuela_data.data:
            raise HTTPException(status_code=404, detail="Perfil de escuela no encontrado.")
        id_escuela = escuela_data.data[0]["idescuela"]
        id_profesor = alumno.idprofesor

    data_final = alumno.model_dump(mode='json')
    data_final["idescuela"] = id_escuela
    data_final["idprofesor"] = id_profesor

    try:
        result = db.table("alumnos").insert(data_final).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al procesar registro: {str(e)}")

@router.get("/", response_model=List[Alumno])
async def listar_alumnos_con_filtro(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")
    
    id_escuela_contexto = None
    query = db.table("alumnos").select("*")
    
    if rol == UserRole.ESCUELA:
        escuela = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if escuela.data:
            id_escuela_contexto = escuela.data[0]["idescuela"]
            query = query.eq("idescuela", id_escuela_contexto)
    elif rol == UserRole.PROFESOR:
        profe = db.table("profesores").select("idprofesor, idescuela").eq("idusuario", id_usuario).execute()
        if profe.data:
            id_escuela_contexto = profe.data[0]["idescuela"]
            query = query.eq("idprofesor", profe.data[0]["idprofesor"])
    
    alumnos_res = query.execute()
    lista_alumnos = alumnos_res.data

    if not lista_alumnos:
        return []

    if id_escuela_contexto:
        pagos_pendientes = db.table("pagos").select("idalumno, monto")\
            .eq("idescuela", id_escuela_contexto)\
            .eq("estatus", 0)\
            .execute()
        
        mapa_deudas = {}
        for p in pagos_pendientes.data:
            alu_id = p["idalumno"]
            monto = float(p["monto"])
            if alu_id not in mapa_deudas:
                mapa_deudas[alu_id] = {"suma": 0.0, "conteo": 0}
            mapa_deudas[alu_id]["suma"] += monto
            mapa_deudas[alu_id]["conteo"] += 1
        
        for alu in lista_alumnos:
            deuda_info = mapa_deudas.get(alu["idalumno"], {"suma": 0.0, "conteo": 0})
            alu["total_deuda"] = deuda_info["suma"]
            alu["conteo_pendientes"] = deuda_info["conteo"]
            alu["pagos_pendientes_detalle"] = []

    return lista_alumnos

@router.get("/{idalumno}", response_model=Alumno)
async def obtener_detalle_alumno(
    idalumno: int,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    # 1. Obtener alumno base
    result = db.table("alumnos").select("*").eq("idalumno", idalumno).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Alumno no encontrado.")
    
    alumno = result.data[0]

    # 2. Obtener desglose de pagos detallado
    pagos_res = db.table("pagos")\
        .select("idpago, monto, concepto, fecharegistro, id_tipo_pago")\
        .eq("idalumno", idalumno)\
        .eq("estatus", 0)\
        .execute()
    
    # 3. Llenar los campos financieros del objeto de respuesta
    alumno["total_deuda"] = sum(float(p["monto"]) for p in pagos_res.data)
    alumno["conteo_pendientes"] = len(pagos_res.data)
    alumno["pagos_pendientes_detalle"] = pagos_res.data
    
    return alumno

@router.post("/{idalumno}/upload-foto", response_model=Alumno)
async def subir_foto_archivo(
    idalumno: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Sube un archivo al Storage de Supabase. 
    Este endpoint es compatible con el flujo de 'Foto al momento' o 'Foto después'.
    """
    alumno_db = await obtener_detalle_alumno(idalumno, current_user, db)
    extension = file.filename.split(".")[-1].lower()
    if extension not in ["jpg", "jpeg", "png"]:
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes JPG o PNG.")

    file_path = f"{idalumno}_{uuid.uuid4()}.{extension}"
    file_content = await file.read()

    try:
        db.storage.from_("alumnos").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": file.content_type}
        )
        foto_url = db.storage.from_("alumnos").get_public_url(file_path)
        update_res = db.table("alumnos").update({"fotoalumno": foto_url}).eq("idalumno", idalumno).execute()
        
        # Recargar para devolver con finanzas actualizadas
        return await obtener_detalle_alumno(idalumno, current_user, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{idalumno}", response_model=Alumno)
async def actualizar_alumno(
    idalumno: int,
    datos: AlumnoUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    await obtener_detalle_alumno(idalumno, current_user, db)
    update_dict = datos.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar.")
    try:
        db.table("alumnos").update(update_dict).eq("idalumno", idalumno).execute()
        # Siempre retornamos vía obtener_detalle_alumno para garantizar datos financieros
        return await obtener_detalle_alumno(idalumno, current_user, db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al actualizar: {str(e)}")