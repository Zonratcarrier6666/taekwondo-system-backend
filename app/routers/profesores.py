from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Query
from typing import List, Optional
from supabase import Client
import uuid
import secrets
import string

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.profesores import Profesor, ProfesorCreate, ProfesorUpdate
from app.schemas.roles import UserRole

# Se elimina el prefix="/profesores" para evitar la duplicidad con el prefijo definido en main.py
router = APIRouter(tags=["Gestión de Profesores"])

@router.get("/", response_model=List[Profesor])
async def listar_profesores_escuela(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Lista los profesores pertenecientes a la escuela del usuario logueado.
    URL Final: /profesores/
    """
    id_usuario = current_user.get("idusuario")
    rol = current_user.get("rol")

    if rol != UserRole.ESCUELA:
        raise HTTPException(status_code=403, detail="Solo las escuelas pueden listar sus profesores.")

    # 1. Obtener idescuela desde la tabla datosescuela
    escuela_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
    if not escuela_res.data:
        raise HTTPException(status_code=404, detail="Perfil de escuela no encontrado.")
    
    id_escuela = escuela_res.data[0]["idescuela"]

    # 2. Filtrar profesores por esa escuela
    result = db.table("profesores").select("*").eq("idescuela", id_escuela).execute()
    return result.data

@router.put("/{idprofesor}", response_model=Profesor)
async def actualizar_profesor_escuela(
    idprofesor: int,
    datos: ProfesorUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Permite a la escuela actualizar los datos de uno de sus profesores.
    """
    id_usuario_escuela = current_user.get("idusuario")
    
    # 1. Validar que el profesor pertenezca a la escuela del solicitante
    escuela_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario_escuela).execute()
    if not escuela_res.data:
         raise HTTPException(status_code=404, detail="Perfil de escuela no encontrado.")
         
    id_escuela = escuela_res.data[0]["idescuela"]

    profe_check = db.table("profesores").select("idescuela").eq("idprofesor", idprofesor).execute()
    if not profe_check.data or profe_check.data[0]["idescuela"] != id_escuela:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este profesor.")

    # 2. Actualizar datos filtrando nulos
    update_data = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar.")

    try:
        result = db.table("profesores").update(update_data).eq("idprofesor", idprofesor).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{idprofesor}/upload-foto", response_model=Profesor)
async def subir_foto_profesor_por_escuela(
    idprofesor: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Permite a la escuela subir o actualizar la foto de uno de sus profesores mediante su ID.
    """
    id_usuario_escuela = current_user.get("idusuario")
    rol = current_user.get("rol")

    if rol != UserRole.ESCUELA:
        raise HTTPException(status_code=403, detail="Solo las escuelas pueden subir fotos de sus profesores.")

    # 1. Validar que el profesor pertenece a la escuela
    esc_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario_escuela).execute()
    id_escuela = esc_res.data[0]["idescuela"]

    profe_check = db.table("profesores").select("idescuela").eq("idprofesor", idprofesor).execute()
    if not profe_check.data or profe_check.data[0]["idescuela"] != id_escuela:
        raise HTTPException(status_code=403, detail="El profesor no pertenece a tu escuela.")

    # 2. Validar archivo
    extension = file.filename.split(".")[-1].lower()
    if extension not in ["jpg", "jpeg", "png"]:
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes JPG o PNG.")

    # 3. Preparar subida
    file_path = f"perfiles/profesor_{idprofesor}_{uuid.uuid4().hex[:8]}.{extension}"
    file_content = await file.read()

    try:
        # Subida al bucket 'alumnos'
        db.storage.from_("alumnos").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": file.content_type}
        )
        foto_url = db.storage.from_("alumnos").get_public_url(file_path)

        # 4. Actualizar tabla
        update_res = db.table("profesores").update({"foto_url": foto_url}).eq("idprofesor", idprofesor).execute()
        return update_res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir la foto: {str(e)}")

@router.get("/mi-perfil", response_model=Profesor)
async def obtener_perfil_propio_profesor(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Permite al profesor ver sus propios datos.
    """
    if current_user.get("rol") != UserRole.PROFESOR:
        raise HTTPException(status_code=403, detail="Ruta exclusiva para profesores.")
    
    id_usuario = current_user.get("idusuario")
    result = db.table("profesores").select("*").eq("idusuario", id_usuario).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    return result.data[0]

@router.post("/upload-foto", response_model=Profesor)
async def subir_foto_profesor_propia(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    El profesor logueado sube su propia foto de perfil.
    """
    if current_user.get("rol") != UserRole.PROFESOR:
        raise HTTPException(status_code=403, detail="Acción exclusiva para profesores.")

    id_usuario = current_user.get("idusuario")
    profe_res = db.table("profesores").select("idprofesor").eq("idusuario", id_usuario).execute()
    if not profe_res.data:
        raise HTTPException(status_code=404, detail="Perfil de profesor no encontrado.")
        
    id_profesor = profe_res.data[0]["idprofesor"]

    extension = file.filename.split(".")[-1].lower()
    if extension not in ["jpg", "jpeg", "png"]:
        raise HTTPException(status_code=400, detail="Formato de imagen inválido.")

    file_path = f"perfiles/profesor_{id_profesor}_{uuid.uuid4().hex[:8]}.{extension}"
    file_content = await file.read()

    try:
        # Subida al bucket 'alumnos' (compartido para imágenes de perfil)
        db.storage.from_("alumnos").upload(
            path=file_path, 
            file=file_content, 
            file_options={"content-type": file.content_type}
        )
        foto_url = db.storage.from_("alumnos").get_public_url(file_path)

        update_res = db.table("profesores").update({"foto_url": foto_url}).eq("idprofesor", id_profesor).execute()
        return update_res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en el servidor de archivos: {str(e)}")

# ─────────────────────────────────────────────────────────────
#  HELPER INTERNO — validar pertenencia de profesor a escuela
# ─────────────────────────────────────────────────────────────

def _get_idescuela_escuela(idusuario: int, db: Client) -> int:
    res = db.table("datosescuela").select("idescuela").eq("idusuario", idusuario).execute()
    if not res.data:
        raise HTTPException(404, "Perfil de escuela no encontrado.")
    return res.data[0]["idescuela"]


def _validar_profe_de_escuela(idprofesor: int, idescuela: int, db: Client) -> dict:
    res = db.table("profesores").select("*").eq("idprofesor", idprofesor).execute()
    if not res.data:
        raise HTTPException(404, "Profesor no encontrado.")
    if res.data[0]["idescuela"] != idescuela:
        raise HTTPException(403, "El profesor no pertenece a tu escuela.")
    return res.data[0]


def _generar_password(longitud: int = 10) -> str:
    """Genera una contraseña segura aleatoria."""
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(chars) for _ in range(longitud))


# ─────────────────────────────────────────────────────────────
#  CREAR PROFESOR — crea usuario + perfil en una sola llamada
# ─────────────────────────────────────────────────────────────

@router.post("/", response_model=Profesor, status_code=201)
async def crear_profesor(
    datos: ProfesorCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Crea un usuario con rol Profesor y su perfil asociado.
    Solo la escuela puede hacerlo.
    Devuelve el perfil del profesor + la contraseña temporal generada
    para que la escuela se la comparta al profesor.
    """
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(403, "Solo las escuelas pueden registrar profesores.")

    idescuela = _get_idescuela_escuela(current_user["idusuario"], db)

    # Verificar que el username no exista
    dup = db.table("usuarios").select("idusuario").eq("username", datos.username).execute()
    if dup.data:
        raise HTTPException(400, f"El usuario '{datos.username}' ya existe.")

    # Generar contraseña temporal
    password_temp = _generar_password()

    try:
        # 1. Crear usuario
        usuario_res = db.table("usuarios").insert({
            "username":  datos.username,
            "password":  password_temp,   # el hash lo maneja tu middleware/auth si aplica
            "rol":       UserRole.PROFESOR,
            "nombre":    datos.nombrecompleto,
        }).execute()

        if not usuario_res.data:
            raise HTTPException(500, "No se pudo crear el usuario.")

        nuevo_idusuario = usuario_res.data[0]["idusuario"]

        # 2. Crear perfil de profesor
        perfil_data = {
            "idusuario":      nuevo_idusuario,
            "idescuela":      idescuela,
            "nombrecompleto": datos.nombrecompleto,
            "especialidad":   getattr(datos, "especialidad", None),
            "telefono":       getattr(datos, "telefono", None),
            "estatus":        1,
        }
        perfil_res = db.table("profesores").insert(perfil_data).execute()

        if not perfil_res.data:
            # Rollback manual del usuario
            db.table("usuarios").delete().eq("idusuario", nuevo_idusuario).execute()
            raise HTTPException(500, "No se pudo crear el perfil del profesor.")

        perfil = perfil_res.data[0]
        # Devolver con la contraseña temporal para que la escuela la entregue
        perfil["_password_temporal"] = password_temp
        return perfil

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Error al crear profesor: {str(e)}")


# ─────────────────────────────────────────────────────────────
#  OBTENER DETALLE DE UN PROFESOR
# ─────────────────────────────────────────────────────────────

@router.get("/{idprofesor}", response_model=Profesor)
async def obtener_profesor(
    idprofesor: int,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Devuelve el perfil completo de un profesor.
    Accesible por la escuela dueña o el propio profesor.
    """
    rol = current_user.get("rol")
    idusuario = current_user.get("idusuario")

    if rol == UserRole.ESCUELA:
        idescuela = _get_idescuela_escuela(idusuario, db)
        return _validar_profe_de_escuela(idprofesor, idescuela, db)

    if rol == UserRole.PROFESOR:
        profe = db.table("profesores").select("*")\
            .eq("idprofesor", idprofesor).eq("idusuario", idusuario).execute()
        if not profe.data:
            raise HTTPException(403, "No puedes ver el perfil de otro profesor.")
        return profe.data[0]

    raise HTTPException(403, "Sin permisos.")


# ─────────────────────────────────────────────────────────────
#  ACTIVAR / DESACTIVAR PROFESOR (baja lógica)
# ─────────────────────────────────────────────────────────────

@router.patch("/{idprofesor}/estatus", response_model=Profesor)
async def cambiar_estatus_profesor(
    idprofesor: int,
    estatus: int = Query(..., ge=0, le=1, description="0 = inactivo, 1 = activo"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Activa (1) o desactiva (0) un profesor sin eliminarlo.
    Al desactivar, sus alumnos NO se reasignan automáticamente —
    la escuela debe hacerlo manualmente desde GestionAlumnos.
    """
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(403, "Solo la escuela puede cambiar el estatus.")

    idescuela = _get_idescuela_escuela(current_user["idusuario"], db)
    _validar_profe_de_escuela(idprofesor, idescuela, db)

    if estatus == 0:
        # Advertir si tiene alumnos activos asignados
        alumnos_activos = db.table("alumnos").select("idalumno", count="exact")\
            .eq("idprofesor", idprofesor).eq("estatus", 1).execute()
        total = alumnos_activos.count or 0
        if total > 0:
            # Se desactiva igual pero se informa en la respuesta
            res = db.table("profesores").update({"estatus": 0})\
                .eq("idprofesor", idprofesor).execute()
            perfil = res.data[0]
            perfil["_advertencia"] = (
                f"Profesor desactivado. Tiene {total} alumno(s) activo(s) sin reasignar."
            )
            return perfil

    res = db.table("profesores").update({"estatus": estatus})\
        .eq("idprofesor", idprofesor).execute()
    return res.data[0]


# ─────────────────────────────────────────────────────────────
#  ELIMINAR PROFESOR (baja física — solo si no tiene alumnos)
# ─────────────────────────────────────────────────────────────

@router.delete("/{idprofesor}", status_code=204)
async def eliminar_profesor(
    idprofesor: int,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Elimina permanentemente el perfil y el usuario del profesor.
    Bloqueado si tiene alumnos asignados (activos o inactivos).
    Recomendado: usar PATCH /estatus primero para desactivar.
    """
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(403, "Solo la escuela puede eliminar profesores.")

    idescuela = _get_idescuela_escuela(current_user["idusuario"], db)
    profe = _validar_profe_de_escuela(idprofesor, idescuela, db)

    # Bloquear si tiene alumnos (activos o inactivos)
    alumnos = db.table("alumnos").select("idalumno", count="exact")\
        .eq("idprofesor", idprofesor).execute()
    if (alumnos.count or 0) > 0:
        raise HTTPException(
            400,
            f"No se puede eliminar: el profesor tiene {alumnos.count} alumno(s) asignado(s). "
            "Reasígnalos primero desde Gestión de Alumnos."
        )

    # Eliminar perfil primero, luego el usuario
    db.table("profesores").delete().eq("idprofesor", idprofesor).execute()
    if profe.get("idusuario"):
        db.table("usuarios").delete().eq("idusuario", profe["idusuario"]).execute()

    return None


# ─────────────────────────────────────────────────────────────
#  REASIGNAR ALUMNOS DE UN PROFESOR A OTRO
# ─────────────────────────────────────────────────────────────

@router.post("/{idprofesor}/reasignar-alumnos", status_code=200)
async def reasignar_alumnos(
    idprofesor: int,
    idprofesor_destino: int = Query(..., description="ID del profesor que recibirá los alumnos"),
    solo_activos: bool = Query(True, description="Si True, solo reasigna alumnos con estatus=1"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Mueve todos los alumnos de un profesor a otro de la misma escuela.
    Útil antes de desactivar o eliminar un profesor.
    """
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(403, "Solo la escuela puede reasignar alumnos.")

    idescuela = _get_idescuela_escuela(current_user["idusuario"], db)
    _validar_profe_de_escuela(idprofesor, idescuela, db)
    _validar_profe_de_escuela(idprofesor_destino, idescuela, db)

    if idprofesor == idprofesor_destino:
        raise HTTPException(400, "El profesor origen y destino deben ser diferentes.")

    query = db.table("alumnos").select("idalumno").eq("idprofesor", idprofesor)
    if solo_activos:
        query = query.eq("estatus", 1)

    alumnos_res = query.execute()
    ids = [a["idalumno"] for a in (alumnos_res.data or [])]

    if not ids:
        return {"reasignados": 0, "mensaje": "No hay alumnos para reasignar."}

    db.table("alumnos").update({"idprofesor": idprofesor_destino})\
        .in_("idalumno", ids).execute()

    return {
        "reasignados": len(ids),
        "mensaje": f"{len(ids)} alumno(s) reasignado(s) al profesor #{idprofesor_destino}.",
    }


# ─────────────────────────────────────────────────────────────
#  RESETEAR CONTRASEÑA (la escuela genera una nueva temporal)
# ─────────────────────────────────────────────────────────────

@router.post("/{idprofesor}/reset-password", status_code=200)
async def reset_password_profesor(
    idprofesor: int,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Genera una nueva contraseña temporal para el profesor.
    La escuela debe entregársela manualmente.
    """
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(403, "Solo la escuela puede resetear contraseñas.")

    idescuela = _get_idescuela_escuela(current_user["idusuario"], db)
    profe = _validar_profe_de_escuela(idprofesor, idescuela, db)

    if not profe.get("idusuario"):
        raise HTTPException(400, "El profesor no tiene usuario asociado.")

    nueva_pass = _generar_password()
    db.table("usuarios").update({"password": nueva_pass})\
        .eq("idusuario", profe["idusuario"]).execute()

    return {
        "ok": True,
        "idprofesor": idprofesor,
        "password_temporal": nueva_pass,
        "mensaje": "Contraseña reseteada. Entrega esta contraseña al profesor de forma segura.",
    }