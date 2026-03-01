from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.utils.database   import get_db
from app.utils.security   import get_password_hash
from app.utils.auth_utils import get_current_user
from app.schemas.usuarios import (
    Usuario, UserRole,
    RegistroEscuelaCompleto, RegistroProfesorCompleto,
    RegistroJuez, RegistroStaff,
)

router = APIRouter(prefix="/usuarios", tags=["Gestión de Usuarios"])


# ─── helpers internos ────────────────────────────────────────

def _require_roles(user: dict, roles: list):
    if user.get("rol") not in roles:
        raise HTTPException(403, "Permisos insuficientes para esta operación.")

def _check_username_libre(username: str, db: Client):
    r = db.table("usuarios").select("idusuario").eq("username", username).execute()
    if r.data:
        raise HTTPException(400, "El nombre de usuario ya está registrado.")


# ─── LISTAR (SuperAdmin) ─────────────────────────────────────

@router.get("/lista", summary="Listar todos los usuarios")
async def listar_usuarios(
    rol: str = None,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_roles(current_user, [UserRole.SUPERADMIN])
    q = db.table("usuarios").select("idusuario, username, rol, fecha_creacion")
    if rol:
        q = q.eq("rol", rol)
    r = q.order("fecha_creacion", desc=True).execute()
    return {"ok": True, "usuarios": r.data or []}


# ─── REGISTRAR ESCUELA (SuperAdmin) ──────────────────────────

@router.post("/registrar-escuela", response_model=Usuario, status_code=201)
async def registrar_escuela(
    datos: RegistroEscuelaCompleto,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_roles(current_user, [UserRole.SUPERADMIN])
    _check_username_libre(datos.username, db)
    try:
        pw = get_password_hash(datos.password)
        res = db.table("usuarios").insert({
            "username": datos.username, "passwordhash": pw, "rol": UserRole.ESCUELA.value,
        }).execute()
        new_user = res.data[0]
        db.table("datosescuela").insert({
            "idusuario":       new_user["idusuario"],
            "nombreescuela":   datos.nombre_escuela,
            "direccion":       datos.direccion,
            "lema":            datos.lema,
            "telefono_oficina": datos.telefono_oficina,
        }).execute()
        return new_user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al registrar escuela: {e}")


# ─── REGISTRAR PROFESOR (SuperAdmin o Escuela) ───────────────

@router.post("/registrar-profesor", response_model=Usuario, status_code=201)
async def registrar_profesor(
    datos: RegistroProfesorCompleto,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_roles(current_user, [UserRole.SUPERADMIN, UserRole.ESCUELA])
    _check_username_libre(datos.username, db)

    # Resolver a qué escuela pertenece el nuevo profesor
    if current_user.get("rol") == UserRole.ESCUELA:
        esc = db.table("datosescuela").select("idescuela") \
            .eq("idusuario", current_user["idusuario"]).execute()
        if not esc.data:
            raise HTTPException(404, "No se encontró perfil de escuela asociado.")
        idescuela = esc.data[0]["idescuela"]
    else:
        # SuperAdmin debe proveer idescuela
        if not datos.idescuela:
            raise HTTPException(400, "Debes indicar la escuela a la que pertenece el profesor.")
        idescuela = datos.idescuela

    try:
        pw = get_password_hash(datos.password)
        res = db.table("usuarios").insert({
            "username": datos.username, "passwordhash": pw, "rol": UserRole.PROFESOR.value,
        }).execute()
        new_user = res.data[0]
        db.table("profesores").insert({
            "idusuario":      new_user["idusuario"],
            "idescuela":      idescuela,
            "nombrecompleto": datos.nombre_completo,
            "idgradodan":     datos.idgradodan,
        }).execute()
        return new_user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al registrar profesor: {e}")


# ─── REGISTRAR JUEZ (SuperAdmin) ─────────────────────────────

@router.post("/registrar-juez", response_model=Usuario, status_code=201)
async def registrar_juez(
    datos: RegistroJuez,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_roles(current_user, [UserRole.SUPERADMIN])
    _check_username_libre(datos.username, db)
    try:
        pw = get_password_hash(datos.password)
        res = db.table("usuarios").insert({
            "username": datos.username, "passwordhash": pw, "rol": UserRole.JUEZ.value,
        }).execute()
        new_user = res.data[0]
        db.table("jueces").insert({
            "idusuario":       new_user["idusuario"],
            "nombre_completo": datos.nombre_completo,
        }).execute()
        return new_user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al registrar juez: {e}")


# ─── REGISTRAR STAFF (SuperAdmin) ────────────────────────────

@router.post("/registrar-staff", response_model=Usuario, status_code=201)
async def registrar_staff(
    datos: RegistroStaff,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Staff = personal de control de acceso en torneos.
    Puede escanear QR, ver datos del competidor y registrar check-in.
    """
    _require_roles(current_user, [UserRole.SUPERADMIN])
    _check_username_libre(datos.username, db)
    try:
        pw = get_password_hash(datos.password)
        res = db.table("usuarios").insert({
            "username": datos.username, "passwordhash": pw, "rol": UserRole.STAFF.value,
        }).execute()
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error al registrar staff: {e}")


# ─── MI PERFIL ───────────────────────────────────────────────

@router.get("/perfil", response_model=dict)
async def obtener_mi_perfil(current_user: dict = Depends(get_current_user)):
    return current_user