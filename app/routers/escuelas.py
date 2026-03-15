from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from supabase import Client
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid

from utils.database import get_db
from utils.auth_utils import get_current_user
from schemas.escuela import Escuela, EscuelaBase, EscuelaUpdate
from schemas.usuarios import UserRole

router = APIRouter(prefix="/escuelas", tags=["Gestión de la Escuela"])


# ─────────────────────────────────────────────────────────────
#  SCHEMAS — Configuración de precios
# ─────────────────────────────────────────────────────────────

class ConfigPrecios(BaseModel):
    mensualidad_default:  float = Field(..., gt=0, description="Monto base de mensualidad")
    inscripcion_default:  float = Field(..., gt=0, description="Monto de inscripción semestral")
    examen_default:       float = Field(..., gt=0, description="Monto de examen de grado")
    recargo_semanal:      float = Field(..., gt=0, description="Recargo por cada semana de atraso")
    dias_gracia:          int   = Field(..., ge=0, le=30, description="Días hábiles sin recargo tras vencimiento")


class ConfigPreciosResponse(BaseModel):
    precios_actuales: dict
    historial:        list
    idescuela:        int


# ─────────────────────────────────────────────────────────────
#  HELPER — obtener idescuela del usuario autenticado
# ─────────────────────────────────────────────────────────────

def _get_idescuela(current_user: dict, db: Client) -> int:
    rol        = current_user.get("rol")
    id_usuario = current_user.get("idusuario")

    if rol == UserRole.ESCUELA:
        res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        if not res.data:
            raise HTTPException(404, "Escuela no encontrada.")
        return res.data[0]["idescuela"]

    elif rol == UserRole.PROFESOR:
        res = db.table("profesores").select("idescuela").eq("idusuario", id_usuario).execute()
        if not res.data:
            raise HTTPException(404, "Perfil de profesor no encontrado.")
        return res.data[0]["idescuela"]

    raise HTTPException(403, "Sin permisos para acceder a configuración de escuela.")


# ─────────────────────────────────────────────────────────────
#  PRECIOS DEFAULT — si la escuela no tiene configuración aún
# ─────────────────────────────────────────────────────────────

PRECIOS_DEFAULT = {
    "mensualidad_default": 400.0,
    "inscripcion_default": 500.0,
    "examen_default":      200.0,
    "recargo_semanal":      50.0,
    "dias_gracia":           5,
}


# ─────────────────────────────────────────────────────────────
#  ENDPOINTS EXISTENTES (sin cambios)
# ─────────────────────────────────────────────────────────────

@router.get("/mi-escuela", response_model=Escuela)
async def obtener_datos_escuela(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    id_usuario = current_user.get("idusuario")
    rol        = current_user.get("rol")

    if rol == UserRole.ESCUELA:
        result = db.table("datosescuela").select("*").eq("idusuario", id_usuario).execute()
    elif rol == UserRole.PROFESOR:
        profe_res = db.table("profesores").select("idescuela").eq("idusuario", id_usuario).execute()
        if not profe_res.data:
            raise HTTPException(status_code=404, detail="Perfil de profesor no encontrado.")
        id_escuela = profe_res.data[0]["idescuela"]
        result = db.table("datosescuela").select("*").eq("idescuela", id_escuela).execute()
    else:
        raise HTTPException(status_code=403, detail="No tienes permisos para ver datos de escuela.")

    if not result.data:
        raise HTTPException(status_code=404, detail="Datos de escuela no encontrados.")

    return result.data[0]


@router.put("/mi-escuela", response_model=Escuela)
async def actualizar_perfil_escuela(
    datos: EscuelaUpdate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(status_code=403, detail="Solo el administrador de la escuela puede editar el perfil.")

    id_usuario  = current_user.get("idusuario")
    update_data = {k: v for k, v in datos.model_dump(exclude_unset=True).items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="No se enviaron datos para actualizar.")

    try:
        result = db.table("datosescuela").update(update_data).eq("idusuario", id_usuario).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="No se pudo encontrar el registro de la escuela.")
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno al actualizar perfil: {str(e)}")


@router.post("/upload-logo", response_model=Escuela)
async def subir_logo_escuela(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(status_code=403, detail="Permisos insuficientes para subir archivos.")

    id_usuario = current_user.get("idusuario")
    escuela_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()

    if not escuela_res.data:
        raise HTTPException(status_code=404, detail="Escuela no encontrada para este usuario.")

    id_escuela = escuela_res.data[0]["idescuela"]
    extension  = file.filename.split(".")[-1].lower()
    file_path  = f"logos/escuela_{id_escuela}_{uuid.uuid4()}.{extension}"
    file_content = await file.read()

    try:
        db.storage.from_("alumnos").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": file.content_type}
        )
        logo_url   = db.storage.from_("alumnos").get_public_url(file_path)
        update_res = db.table("datosescuela").update({"logo_url": logo_url}).eq("idescuela", id_escuela).execute()
        return update_res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar la imagen: {str(e)}")


# ─────────────────────────────────────────────────────────────
#  NUEVO — GET /escuelas/configuracion/precios
#  Devuelve precios actuales + historial completo de cambios
# ─────────────────────────────────────────────────────────────

@router.get("/configuracion/precios")
async def obtener_precios(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Retorna la configuración de precios vigente de la escuela
    junto con el historial completo de cambios para auditoría.
    """
    idescuela  = _get_idescuela(current_user, db)
    esc_res    = db.table("datosescuela").select("idescuela, config_json")\
                   .eq("idescuela", idescuela).execute()

    if not esc_res.data:
        raise HTTPException(404, "Escuela no encontrada.")

    config     = esc_res.data[0].get("config_json") or {}
    precios    = config.get("precios", PRECIOS_DEFAULT.copy())
    historial  = config.get("historial_precios", [])

    return {
        "ok":              True,
        "idescuela":       idescuela,
        "precios_actuales": precios,
        "historial":       historial,  # lista ordenada desc por fecha
    }


# ─────────────────────────────────────────────────────────────
#  NUEVO — PUT /escuelas/configuracion/precios
#  Actualiza precios y guarda el snapshot anterior en historial
# ─────────────────────────────────────────────────────────────

@router.put("/configuracion/precios")
async def actualizar_precios(
    body: ConfigPrecios,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Actualiza los precios de la escuela.
    - Guarda un snapshot de los precios ANTERIORES en historial_precios
      con fecha y usuario que hizo el cambio — para auditoría completa.
    - Solo rol Escuela puede modificar precios.
    """
    if current_user.get("rol") != UserRole.ESCUELA:
        raise HTTPException(403, "Solo el administrador de la escuela puede modificar precios.")

    idescuela  = _get_idescuela(current_user, db)
    username   = current_user.get("username") or current_user.get("sub") or "sistema"

    # 1. Leer config actual
    esc_res = db.table("datosescuela").select("config_json")\
                .eq("idescuela", idescuela).execute()
    if not esc_res.data:
        raise HTTPException(404, "Escuela no encontrada.")

    config   = esc_res.data[0].get("config_json") or {}
    precios_anteriores = config.get("precios", None)
    historial          = config.get("historial_precios", [])

    # 2. Armar nuevos precios con metadata
    nuevos_precios = {
        **body.model_dump(),
        "actualizado_en":  datetime.now().strftime("%Y-%m-%d"),
        "actualizado_por": username,
    }

    # 3. Si había precios anteriores, guardar snapshot en historial
    if precios_anteriores:
        entrada_historial = {
            "fecha":          precios_anteriores.get("actualizado_en", "—"),
            "actualizado_por": precios_anteriores.get("actualizado_por", "—"),
            "precios": {
                k: v for k, v in precios_anteriores.items()
                if k not in ("actualizado_en", "actualizado_por")
            },
        }
        # Insertar al inicio (más reciente primero) y limitar a 50 entradas
        historial = [entrada_historial, *historial][:50]

    # 4. Guardar en config_json
    config["precios"]          = nuevos_precios
    config["historial_precios"] = historial

    db.table("datosescuela")\
      .update({"config_json": config})\
      .eq("idescuela", idescuela)\
      .execute()

    return {
        "ok":               True,
        "idescuela":        idescuela,
        "precios_actuales": nuevos_precios,
        "historial":        historial,
        "mensaje":          f"Precios actualizados por {username} el {nuevos_precios['actualizado_en']}",
    }


# ─────────────────────────────────────────────────────────────
#  NUEVO — GET /escuelas/configuracion/precios/historial
#  Solo el historial, útil para mostrar tabla de auditoría
# ─────────────────────────────────────────────────────────────

@router.get("/configuracion/precios/historial")
async def historial_precios(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Devuelve el historial completo de cambios de precios.
    Cada entrada incluye fecha, quién lo cambió y los valores vigentes en ese momento.
    """
    idescuela = _get_idescuela(current_user, db)
    esc_res   = db.table("datosescuela").select("config_json")\
                  .eq("idescuela", idescuela).execute()

    if not esc_res.data:
        raise HTTPException(404, "Escuela no encontrada.")

    config   = esc_res.data[0].get("config_json") or {}
    historial = config.get("historial_precios", [])

    return {
        "ok":       True,
        "idescuela": idescuela,
        "total":    len(historial),
        "historial": historial,
    }


# ─────────────────────────────────────────────────────────────
#  NUEVO — GET /escuelas/configuracion/precios/vigentes
#  Endpoint público (solo auth) para que pagos.py y mensualidades.py
#  lean los precios sin importar el rol
# ─────────────────────────────────────────────────────────────

@router.get("/configuracion/precios/vigentes/{idescuela}")
async def precios_vigentes(
    idescuela: int,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Devuelve solo los precios actuales de una escuela.
    Usado internamente por pagos.py y mensualidades.py al generar cargos.
    """
    esc_res = db.table("datosescuela").select("config_json")\
                .eq("idescuela", idescuela).execute()

    if not esc_res.data:
        raise HTTPException(404, "Escuela no encontrada.")

    config  = esc_res.data[0].get("config_json") or {}
    precios = config.get("precios", PRECIOS_DEFAULT.copy())

    # Asegurar que todos los campos están presentes (retrocompatibilidad)
    for k, v in PRECIOS_DEFAULT.items():
        precios.setdefault(k, v)

    return {
        "ok":       True,
        "idescuela": idescuela,
        "precios":  precios,
    }