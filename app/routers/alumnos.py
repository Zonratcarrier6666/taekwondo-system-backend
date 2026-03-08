from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from typing import List
from supabase import Client
import uuid
import os

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.alumnos import Alumno, AlumnoCreate, AlumnoUpdate
from app.schemas.roles import UserRole

router = APIRouter()

@router.post("/", response_model=Alumno, status_code=status.HTTP_201_CREATED)
async def registrar_alumno_predictivo(
    alumno: AlumnoCreate, 
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Registra los datos básicos de un alumno.
    - Si hay UN solo profesor en la escuela → se asigna automáticamente.
    - Si hay MÁS de uno → se guarda sin profesor (idprofesor = null).
      El alumno queda bloqueado hasta asignarse vía PUT /{idalumno}/asignar-profesor.
    """
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")
    
    if rol not in [UserRole.ESCUELA, UserRole.PROFESOR]:
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar alumnos.")

    id_escuela = None
    id_profesor = None

    if rol == UserRole.PROFESOR:
        # Profesor siempre se asigna a sí mismo
        profe_data = db.table("profesores").select("idprofesor, idescuela").eq("idusuario", id_usuario).execute()
        if not profe_data.data:
            raise HTTPException(status_code=404, detail="Perfil de profesor no encontrado.")
        id_profesor = profe_data.data[0]["idprofesor"]
        id_escuela  = profe_data.data[0]["idescuela"]
        
    elif rol == UserRole.ESCUELA:
        escuela_data = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if not escuela_data.data:
            raise HTTPException(status_code=404, detail="Perfil de escuela no encontrado.")
        id_escuela = escuela_data.data[0]["idescuela"]

        # Contar profesores activos de la escuela
        profesores_res = db.table("profesores")\
            .select("idprofesor")\
            .eq("idescuela", id_escuela)\
            .execute()
        profesores = profesores_res.data or []

        if len(profesores) == 1:
            # Auto-asignar al único profesor
            id_profesor = profesores[0]["idprofesor"]
        elif len(profesores) > 1:
            # Si el frontend manda uno explícitamente, usarlo; si no, null (pendiente)
            id_profesor = alumno.idprofesor if alumno.idprofesor else None
        else:
            # Sin profesores — bloquear registro
            raise HTTPException(
                status_code=400,
                detail="No puedes registrar alumnos porque la escuela no tiene profesores registrados. "
                       "Agrega al menos un profesor primero."
            )

    data_final = alumno.model_dump(mode='json')
    data_final["idescuela"] = id_escuela
    data_final["idprofesor"] = id_profesor

    try:
        result = db.table("alumnos").insert(data_final).execute()
        alumno_creado = result.data[0]
        # Indicar al frontend si el alumno quedó sin profesor
        alumno_creado["_sin_profesor"] = id_profesor is None
        return alumno_creado
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
        return await obtener_detalle_alumno(idalumno, current_user, db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al actualizar: {str(e)}")


# ─────────────────────────────────────────────────────────────
#  HELPER — verifica que el alumno tenga profesor asignado
#  Llamar desde pagos, torneos, etc. antes de operar
# ─────────────────────────────────────────────────────────────
async def verificar_alumno_activo(idalumno: int, db: Client) -> dict:
    """
    Lanza 403 si el alumno no tiene profesor asignado.
    Usar en endpoints de pagos, inscripciones, exámenes, etc.

    Ejemplo de uso en pagos.py:
        from app.routers.alumnos import verificar_alumno_activo
        await verificar_alumno_activo(idalumno, db)
    """
    res = db.table("alumnos").select("idalumno, idprofesor, nombres, apellidopaterno")\
        .eq("idalumno", idalumno).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Alumno no encontrado.")
    alumno = res.data[0]
    if not alumno.get("idprofesor"):
        nombre = f"{alumno.get('nombres', '')} {alumno.get('apellidopaterno', '')}".strip()
        raise HTTPException(
            status_code=403,
            detail=f"El alumno '{nombre}' no tiene profesor asignado. "
                   f"Asígnalo a un profesor antes de continuar."
        )
    return alumno


# ─────────────────────────────────────────────────────────────
#  ASIGNAR PROFESOR A ALUMNO
# ─────────────────────────────────────────────────────────────
@router.put("/{idalumno}/asignar-profesor", response_model=Alumno)
async def asignar_profesor(
    idalumno:    int,
    idprofesor:  int,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Asigna o cambia el profesor de un alumno.
    Solo rol Escuela puede hacerlo.
    El profesor debe pertenecer a la misma escuela del alumno.
    """
    rol = current_user.get("rol")
    if rol != UserRole.ESCUELA:
        raise HTTPException(status_code=403, detail="Solo la escuela puede asignar profesores.")

    # Verificar que el alumno existe y pertenece a esta escuela
    alumno_res = db.table("alumnos").select("idalumno, idescuela, nombres, apellidopaterno")\
        .eq("idalumno", idalumno).execute()
    if not alumno_res.data:
        raise HTTPException(status_code=404, detail="Alumno no encontrado.")
    alumno = alumno_res.data[0]

    id_usuario = current_user.get("idusuario")
    escuela_res = db.table("datosescuela").select("idescuela")\
        .eq("idusuario", id_usuario).execute()
    if not escuela_res.data:
        raise HTTPException(status_code=404, detail="Escuela no encontrada.")
    id_escuela = escuela_res.data[0]["idescuela"]

    if alumno["idescuela"] != id_escuela:
        raise HTTPException(status_code=403, detail="El alumno no pertenece a tu escuela.")

    # Verificar que el profesor pertenece a la misma escuela
    profe_res = db.table("profesores").select("idprofesor, idescuela")\
        .eq("idprofesor", idprofesor).execute()
    if not profe_res.data:
        raise HTTPException(status_code=404, detail="Profesor no encontrado.")
    if profe_res.data[0]["idescuela"] != id_escuela:
        raise HTTPException(status_code=403, detail="El profesor no pertenece a tu escuela.")

    # Asignar
    db.table("alumnos").update({"idprofesor": idprofesor})\
        .eq("idalumno", idalumno).execute()

    return await obtener_detalle_alumno(idalumno, current_user, db)


# ─────────────────────────────────────────────────────────────
#  LISTAR PROFESORES DE LA ESCUELA (para el selector del frontend)
# ─────────────────────────────────────────────────────────────
@router.get("/escuela/profesores")
async def listar_profesores_escuela(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Devuelve los profesores de la escuela del usuario autenticado.
    Útil para el selector al asignar profesor a un alumno.
    """
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")

    if rol == UserRole.ESCUELA:
        escuela_res = db.table("datosescuela").select("idescuela")\
            .eq("idusuario", id_usuario).execute()
        if not escuela_res.data:
            raise HTTPException(status_code=404, detail="Escuela no encontrada.")
        id_escuela = escuela_res.data[0]["idescuela"]
    elif rol == UserRole.PROFESOR:
        profe_res = db.table("profesores").select("idescuela")\
            .eq("idusuario", id_usuario).execute()
        if not profe_res.data:
            raise HTTPException(status_code=404, detail="Perfil no encontrado.")
        id_escuela = profe_res.data[0]["idescuela"]
    else:
        raise HTTPException(status_code=403, detail="Sin permisos.")

    profesores_res = db.table("profesores")\
        .select("idprofesor, usuarios(username, nombre)")\
        .eq("idescuela", id_escuela)\
        .execute()

    resultado = []
    for p in profesores_res.data or []:
        u = p.get("usuarios") or {}
        resultado.append({
            "idprofesor": p["idprofesor"],
            "nombre":     u.get("nombre") or u.get("username") or f"Profesor #{p['idprofesor']}",
            "username":   u.get("username", ""),
        })

    return {
        "ok":         True,
        "profesores": resultado,
        "total":      len(resultado),
    }