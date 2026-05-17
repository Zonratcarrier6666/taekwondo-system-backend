from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel, EmailStr
from supabase import Client
import re, uuid

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

    # Escola
    grado_escolar:      Optional[str]   = None
    escuela_procedencia: Optional[str]  = None
    idprofesor: Optional[int] = None
    # Foto: se sube por separado via POST /{slug}/foto/{idalumno}


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
    - Foto: se sube por separado via POST /{slug}/foto/{idalumno}
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

    foto_url = None  # foto se sube por separado

    # Preparar contacto según edad
    telefono = payload.telefono_propio if payload.es_mayor_de_edad else payload.telefonocontacto
    correo   = payload.correo_propio   if payload.es_mayor_de_edad else payload.correotutor
    tutor    = None if payload.es_mayor_de_edad else payload.nombretutor

    alumno = {
        "idescuela":                idescuela,
        "idprofesor":  payload.idprofesor or None,
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

    nuevo         = result.data[0]
    nuevo_id      = nuevo["idalumno"]
    from datetime import date
    import calendar
    fecha_hoy = date.today()
    dia_cobro = fecha_hoy.day

    # La primera mensualidad vence el mes SIGUIENTE al de inscripción.
    # Ej: inscripción el 5 de mayo → primer cobro el 5 de junio.
    if fecha_hoy.month == 12:
        anio_cobro = fecha_hoy.year + 1
        mes_cobro  = 1
    else:
        anio_cobro = fecha_hoy.year
        mes_cobro  = fecha_hoy.month + 1

    # Ajustar si el mes siguiente tiene menos días (ej: día 31 → febrero tiene 28)
    dia_real = min(dia_cobro, calendar.monthrange(anio_cobro, mes_cobro)[1])
    mes_str  = f"{anio_cobro}-{mes_cobro:02d}"

    # ── 1. Guardar dia_cobro y monto en config_json de la escuela ──
    try:
        esc_res = db.table("datosescuela").select("config_json")\
            .eq("idescuela", idescuela).execute()
        config  = (esc_res.data[0].get("config_json") or {}) if esc_res.data else {}
        precios = config.get("precios", {})
        monto   = float(precios.get("mensualidad_default", 400.0))
        recargo = float(precios.get("recargo_semanal", 50.0))
        gracia  = int(precios.get("dias_gracia", 5))

        config[f"pago_alumno_{nuevo_id}"] = {
            "monto_mensualidad": monto,
            "dia_cobro":         dia_cobro,
            "actualizado_en":    str(fecha_hoy),
        }
        db.table("datosescuela").update({"config_json": config})\
            .eq("idescuela", idescuela).execute()
    except Exception as e:
        print(f"[INSCRIPCION] Error guardando config alumno {nuevo_id}: {e}")
        monto   = 400.0
        recargo = 50.0
        gracia  = 5

    # ── 2. Generar primer cargo de mensualidad (vence el mes siguiente) ───────
    primer_cargo_ok = False
    try:
        fecha_venc = str(date(anio_cobro, mes_cobro, dia_real))
        db.table("pagos").insert({
            "idalumno":     nuevo_id,
            "idescuela":    idescuela,
            "id_tipo_pago": 1,
            "monto":        monto,
            "concepto":     f"Mensualidad {mes_str}",
            "folio_recibo": f"TKW-{uuid.uuid4().hex[:8].upper()}",
            "estatus":      0,
            "fecha_pago":   fecha_venc,
            "desglose_interno": {
                "tipo":                    "mensualidad",
                "mes":                     mes_str,
                "dia_cobro":               dia_cobro,
                "precio_vigente":          monto,
                "recargo_semanal_vigente": recargo,
                "dias_gracia_vigente":     gracia,
                "precio_tomado_en":        str(fecha_hoy),
                "generado_por":            "inscripcion_publica",
            },
        }).execute()
        primer_cargo_ok = True
    except Exception as e:
        # No bloquear el registro si falla el cargo
        print(f"[INSCRIPCION] Error generando cargo mensualidad alumno {nuevo_id}: {e}")

    return {
        "message":               "Alumno registrado exitosamente",
    "idalumno":              nuevo_id,
    "nombres":               nuevo["nombres"],
    "apellidos":             f"{nuevo['apellidopaterno']} {nuevo.get('apellidomaterno','') or ''}".strip(),
    "idprofesor":            payload.idprofesor or None,   # ← agregar esta línea
    "dia_cobro":             dia_cobro,
    "primer_cargo_mes":      mes_str,
    "primer_cargo_generado": primer_cargo_ok,
    }




# ─────────────────────────────────────────────────────────────
#  POST /inscripcion/:slug/foto/:idalumno — subir foto pública
# ─────────────────────────────────────────────────────────────

@router.post("/{slug}/foto/{idalumno}", status_code=200)
async def subir_foto_publica(
    slug: str,
    idalumno: int,
    file: UploadFile = File(...),
    db: Client = Depends(get_db),
):
    """
    Sube la foto del alumno recién registrado al bucket de Supabase.
    No requiere autenticación — es parte del flujo público de inscripción.
    """
    # Verificar que el alumno exista y pertenezca a esta escuela
    escuela = _get_escuela_by_slug(slug, db)
    alumno = db.table("alumnos").select("idalumno").eq("idalumno", idalumno).eq("idescuela", escuela["idescuela"]).execute()
    if not alumno.data:
        raise HTTPException(404, "Alumno no encontrado.")

    extension = file.filename.split(".")[-1].lower() if file.filename else "jpg"
    if extension not in ["jpg", "jpeg", "png"]:
        raise HTTPException(400, "Solo se permiten imágenes JPG o PNG.")

    file_path = f"{idalumno}_{uuid.uuid4()}.{extension}"
    file_content = await file.read()

    try:
        db.storage.from_("alumnos").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": file.content_type}
        )
        foto_url = db.storage.from_("alumnos").get_public_url(file_path)
        db.table("alumnos").update({"fotoalumno": foto_url}).eq("idalumno", idalumno).execute()
        return {"ok": True, "fotoalumno": foto_url}
    except Exception as e:
        raise HTTPException(500, f"Error al subir foto: {str(e)}")

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