from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel, EmailStr
from supabase import Client
import re, uuid, base64

from utils.database import get_db

router = APIRouter(tags=["Inscripción Pública"])


# ─────────────────────────────────────────────────────────────
#  HELPER — slug a idescuela
# ─────────────────────────────────────────────────────────────

def _slugify(nombre: str) -> str:
    s = nombre.lower().strip()
    s = re.sub(r'[áàä]', 'a', s)
    s = re.sub(r'[éèë]', 'e', s)
    s = re.sub(r'[íìï]', 'i', s)
    s = re.sub(r'[óòö]', 'o', s)
    s = re.sub(r'[úùü]', 'u', s)
    s = re.sub(r'[ñ]', 'n', s)
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')

def _get_escuela_by_slug(slug: str, db: Client) -> dict:
    """Busca escuela por slug generado de su nombre."""
    result = db.table("datosescuela").select("*").execute()
    for e in result.data:
        if _slugify(e["nombreescuela"]) == slug:
            return e
    raise HTTPException(404, f"Escuela no encontrada: '{slug}'")


# ─────────────────────────────────────────────────────────────
#  GET /inscripcion/:slug — datos públicos de la escuela
# ─────────────────────────────────────────────────────────────

@router.get("/{slug}")
async def obtener_info_escuela(slug: str, db: Client = Depends(get_db)):
    """
    Retorna datos públicos de la escuela para mostrar en el formulario.
    No requiere autenticación.
    """
    escuela = _get_escuela_by_slug(slug, db)
    return {
        "idescuela":     escuela["idescuela"],
        "nombreescuela": escuela["nombreescuela"],
        "logo_url":      escuela.get("logo_url"),
        "lema":          escuela.get("lema"),
        "direccion":     escuela.get("direccion"),
        "slug":          slug,
    }


# ─────────────────────────────────────────────────────────────
#  SCHEMA — datos del formulario
# ─────────────────────────────────────────────────────────────

class InscripcionPayload(BaseModel):
    # Identificación
    nombres:            str
    apellidopaterno:    str
    apellidomaterno:    Optional[str]   = None
    fechanacimiento:    str             # ISO: YYYY-MM-DD
    es_mayor_de_edad:   bool            = False

    # Tutor legal (solo menores)
    nombretutor:        Optional[str]   = None
    telefonocontacto:   Optional[str]   = None
    correotutor:        Optional[str]   = None

    # Datos propios si es mayor
    telefono_propio:    Optional[str]   = None
    correo_propio:      Optional[str]   = None

    # Domicilio
    direcciondomicilio: Optional[str]   = None

    # Médicos
    tipo_sangre:        Optional[str]   = None
    alergias:           Optional[str]   = "Ninguna"
    padecimientos_cronicos: Optional[str] = "Ninguno"

    # Seguro
    seguro_medico:      Optional[str]   = "No cuenta"
    nss_o_poliza:       Optional[str]   = None

    # Emergencia
    contacto_emergencia_nombre: Optional[str] = None
    contacto_emergencia_tel:    Optional[str] = None

    # Escolar
    grado_escolar:      Optional[str]   = None
    escuela_procedencia: Optional[str]  = None

    # Foto (base64 opcional — se puede subir después)
    foto_base64:        Optional[str]   = None


# ─────────────────────────────────────────────────────────────
#  POST /inscripcion/:slug — guardar alumno en BD
# ─────────────────────────────────────────────────────────────

@router.post("/{slug}", status_code=201)
async def registrar_alumno(
    slug: str,
    payload: InscripcionPayload,
    db: Client = Depends(get_db),
):
    """
    Registra un nuevo alumno directamente en la BD desde el formulario público.
    - Si es mayor de edad: usa sus propios datos de contacto
    - Si es menor: usa datos del tutor
    - Foto: si viene en base64 se sube a Supabase Storage
    - Alumno queda activo (estatus=1) de inmediato
    """
    escuela = _get_escuela_by_slug(slug, db)
    idescuela = escuela["idescuela"]

    # Verificar que no exista ya (mismo nombre + fecha nacimiento + escuela)
    dup = db.table("alumnos")\
        .select("idalumno")\
        .eq("idescuela", idescuela)\
        .eq("nombres", payload.nombres.strip())\
        .eq("apellidopaterno", payload.apellidopaterno.strip())\
        .eq("fechanacimiento", payload.fechanacimiento)\
        .execute()
    if dup.data:
        raise HTTPException(409, "Ya existe un alumno con ese nombre y fecha de nacimiento en esta escuela.")

    # Subir foto si viene en base64
    foto_url = None
    if payload.foto_base64:
        try:
            header, data = payload.foto_base64.split(",", 1) if "," in payload.foto_base64 else ("", payload.foto_base64)
            ext = "jpg"
            if "png" in header: ext = "png"
            img_bytes = base64.b64decode(data)
            filename = f"alumnos/{idescuela}/{uuid.uuid4()}.{ext}"
            db.storage.from_("fotos").upload(filename, img_bytes, {"content-type": f"image/{ext}"})
            foto_url = db.storage.from_("fotos").get_public_url(filename)
        except Exception:
            foto_url = None  # foto falla silenciosamente, no bloquea el registro

    # Preparar contacto según edad
    telefono = payload.telefono_propio if payload.es_mayor_de_edad else payload.telefonocontacto
    correo   = payload.correo_propio   if payload.es_mayor_de_edad else payload.correotutor
    tutor    = None if payload.es_mayor_de_edad else payload.nombretutor

    alumno = {
        "idescuela":                idescuela,
        "nombres":                  payload.nombres.strip(),
        "apellidopaterno":          payload.apellidopaterno.strip(),
        "apellidomaterno":          payload.apellidomaterno,
        "fechanacimiento":          payload.fechanacimiento,
        "nombretutor":              tutor,
        "telefonocontacto":         telefono,
        "correotutor":              correo,
        "direcciondomicilio":       payload.direcciondomicilio,
        "tipo_sangre":              payload.tipo_sangre,
        "alergias":                 payload.alergias or "Ninguna",
        "padecimientos_cronicos":   payload.padecimientos_cronicos or "Ninguno",
        "seguro_medico":            payload.seguro_medico or "No cuenta",
        "nss_o_poliza":             payload.nss_o_poliza,
        "contacto_emergencia_nombre": payload.contacto_emergencia_nombre,
        "contacto_emergencia_tel":  payload.contacto_emergencia_tel,
        "grado_escolar":            payload.grado_escolar,
        "escuela_procedencia":      payload.escuela_procedencia,
        "fotoalumno":               foto_url,
        "idgradoactual":            1,   # cinta blanca por defecto
        "estatus":                  1,   # activo de inmediato
    }

    result = db.table("alumnos").insert(alumno).execute()
    if not result.data:
        raise HTTPException(500, "Error al registrar el alumno.")

    nuevo = result.data[0]
    return {
        "message":   "Alumno registrado exitosamente",
        "idalumno":  nuevo["idalumno"],
        "nombres":   nuevo["nombres"],
        "apellidos": f"{nuevo['apellidopaterno']} {nuevo.get('apellidomaterno','') or ''}".strip(),
    }


# ─────────────────────────────────────────────────────────────
#  GET /inscripcion/:slug/link — genera la URL pública
#  (para que la escuela la copie/comparta)
# ─────────────────────────────────────────────────────────────

@router.get("/{slug}/link-info")
async def info_link(slug: str, db: Client = Depends(get_db)):
    escuela = _get_escuela_by_slug(slug, db)
    return {
        "slug": slug,
        "nombreescuela": escuela["nombreescuela"],
        "url_sugerida": f"/registro/{slug}",
    }