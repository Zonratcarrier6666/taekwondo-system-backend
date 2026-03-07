from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel
from supabase import Client

from utils.database import get_db
from utils.auth_utils import get_current_user
from schemas.cintagrados import Cinta, HistorialGrado
from schemas.examen import PromocionManual
from schemas.usuarios import UserRole
from schemas.pagos import TipoPago, EstatusPago

router = APIRouter(tags=["Cintas y Grados"])


# ─────────────────────────────────────────────────────────────
#  SCHEMAS inline para CRUD de cintas por escuela
# ─────────────────────────────────────────────────────────────

class CintaEscuelaCreate(BaseModel):
    nivelkupdan: str
    color: str
    color_stripe: Optional[str] = None  # franja secundaria
    significado: Optional[str] = None
    orden: Optional[int] = None

class CintaEscuelaUpdate(BaseModel):
    nivelkupdan: Optional[str] = None
    color: Optional[str] = None
    color_stripe: Optional[str] = None
    significado: Optional[str] = None
    orden: Optional[int] = None

class CintaEscuelaOut(BaseModel):
    idgrado: int
    idescuela: Optional[int]
    nivelkupdan: str
    color: str
    color_stripe: Optional[str]
    significado: Optional[str]
    orden: Optional[int]


# ─────────────────────────────────────────────────────────────
#  HELPER — obtener idescuela del usuario logueado
# ─────────────────────────────────────────────────────────────

def _get_idescuela(user: dict, db: Client) -> int:
    rol = user.get("rol")
    idusuario = user.get("idusuario")

    if rol == UserRole.ESCUELA:
        r = db.table("datosescuela").select("idescuela").eq("idusuario", idusuario).execute()
        if not r.data:
            raise HTTPException(404, "Escuela no encontrada para este usuario")
        return r.data[0]["idescuela"]

    if rol == UserRole.PROFESOR:
        r = db.table("profesores").select("idescuela").eq("idusuario", idusuario).execute()
        if not r.data:
            raise HTTPException(404, "Profesor no encontrado")
        return r.data[0]["idescuela"]

    raise HTTPException(403, "Sin permisos para gestionar cintas")


# ─────────────────────────────────────────────────────────────
#  CATÁLOGO GLOBAL (sin auth — para selects en formularios)
# ─────────────────────────────────────────────────────────────

@router.get("/", response_model=List[Cinta])
async def listar_catalogo_cintas(db: Client = Depends(get_db)):
    """Retorna el catálogo completo de cintas kup/dan."""
    try:
        result = db.table("cintasgrados").select("*").order("idgrado").execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────
#  CRUD — cintas propias de la escuela
# ─────────────────────────────────────────────────────────────

@router.get("/mi-escuela", response_model=List[CintaEscuelaOut])
async def listar_cintas_escuela(
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Lista las cintas propias de la escuela.
    Si no tiene ninguna definida, devuelve el catálogo global como fallback.
    """
    idescuela = _get_idescuela(user, db)

    propias = db.table("cintasgrados")\
        .select("*")\
        .eq("idescuela", idescuela)\
        .order("orden", nullsfirst=False)\
        .order("idgrado")\
        .execute()

    if propias.data:
        return propias.data

    # Fallback: catálogo global (idescuela IS NULL)
    globales = db.table("cintasgrados")\
        .select("*")\
        .is_("idescuela", "null")\
        .order("idgrado")\
        .execute()
    return globales.data


@router.post("/mi-escuela", response_model=CintaEscuelaOut, status_code=201)
async def crear_cinta_escuela(
    body: CintaEscuelaCreate,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Crea una nueva cinta para la escuela."""
    idescuela = _get_idescuela(user, db)

    dup = db.table("cintasgrados")\
        .select("idgrado")\
        .eq("idescuela", idescuela)\
        .eq("nivelkupdan", body.nivelkupdan)\
        .execute()
    if dup.data:
        raise HTTPException(400, f"Ya existe una cinta '{body.nivelkupdan}' en tu escuela")

    r = db.table("cintasgrados").insert({
        "idescuela": idescuela,
        "nivelkupdan": body.nivelkupdan,
        "color": body.color,
        "color_stripe": body.color_stripe,
        "significado": body.significado,
        "orden": body.orden,
    }).execute()

    if not r.data:
        raise HTTPException(500, "No se pudo crear la cinta")
    return r.data[0]


@router.put("/mi-escuela/{idgrado}", response_model=CintaEscuelaOut)
async def actualizar_cinta_escuela(
    idgrado: int,
    body: CintaEscuelaUpdate,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Edita una cinta. Solo puede editar las que pertenecen a su escuela."""
    idescuela = _get_idescuela(user, db)

    existing = db.table("cintasgrados")\
        .select("idgrado")\
        .eq("idgrado", idgrado)\
        .eq("idescuela", idescuela)\
        .execute()
    if not existing.data:
        raise HTTPException(404, "Cinta no encontrada o no pertenece a tu escuela")

    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    if not payload:
        raise HTTPException(400, "Nada que actualizar")

    r = db.table("cintasgrados")\
        .update(payload)\
        .eq("idgrado", idgrado)\
        .execute()

    if not r.data:
        raise HTTPException(500, "No se pudo actualizar la cinta")
    return r.data[0]


@router.delete("/mi-escuela/{idgrado}", status_code=204)
async def eliminar_cinta_escuela(
    idgrado: int,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Elimina una cinta de la escuela.
    Bloquea si hay alumnos con ese grado como activo.
    """
    idescuela = _get_idescuela(user, db)

    existing = db.table("cintasgrados")\
        .select("idgrado")\
        .eq("idgrado", idgrado)\
        .eq("idescuela", idescuela)\
        .execute()
    if not existing.data:
        raise HTTPException(404, "Cinta no encontrada o no pertenece a tu escuela")

    en_uso = db.table("alumnos")\
        .select("idalumno")\
        .eq("idgradoactual", idgrado)\
        .eq("idescuela", idescuela)\
        .execute()
    if en_uso.data:
        raise HTTPException(
            400,
            f"No se puede eliminar: {len(en_uso.data)} alumno(s) tienen esta cinta como grado actual"
        )

    db.table("cintasgrados").delete().eq("idgrado", idgrado).execute()
    return None


@router.post("/mi-escuela/importar-global", status_code=201)
async def importar_catalogo_global(
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Copia el catálogo global a la escuela para que pueda personalizarlo.
    Solo funciona si la escuela no tiene cintas propias todavía.
    """
    idescuela = _get_idescuela(user, db)

    propias = db.table("cintasgrados")\
        .select("idgrado")\
        .eq("idescuela", idescuela)\
        .execute()
    if propias.data:
        raise HTTPException(400, "Tu escuela ya tiene un catálogo propio.")

    globales = db.table("cintasgrados")\
        .select("*")\
        .is_("idescuela", "null")\
        .order("idgrado")\
        .execute()
    if not globales.data:
        raise HTTPException(404, "No hay catálogo global para importar")

    nuevas = [
        {
            "idescuela": idescuela,
            "nivelkupdan": c["nivelkupdan"],
            "color": c["color"],
            "significado": c.get("significado"),
            "orden": i + 1,
        }
        for i, c in enumerate(globales.data)
    ]

    r = db.table("cintasgrados").insert(nuevas).execute()
    return {
        "importadas": len(r.data),
        "mensaje": "Catálogo global importado. Ahora puedes personalizarlo."
    }


# ─────────────────────────────────────────────────────────────
#  PROMOCIÓN MANUAL (existente — sin cambios)
# ─────────────────────────────────────────────────────────────

@router.post("/promocionar-manual", status_code=status.HTTP_200_OK)
async def promocionar_alumno_individual(
    datos: PromocionManual,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    rol = current_user.get("rol")
    id_usuario = current_user.get("idusuario")

    if rol not in [UserRole.ESCUELA, UserRole.PROFESOR]:
        raise HTTPException(status_code=403, detail="No tienes permisos para realizar promociones.")

    alumno_res = db.table("alumnos").select("idalumno, idescuela, idprofesor, idgradoactual").eq("idalumno", datos.idalumno).execute()
    if not alumno_res.data:
        raise HTTPException(status_code=404, detail="Alumno no encontrado.")

    alumno = alumno_res.data[0]
    id_grado_anterior = alumno["idgradoactual"]
    id_escuela = alumno["idescuela"]

    if id_grado_anterior == datos.id_nuevo_grado:
        raise HTTPException(status_code=400, detail="El alumno ya posee ese grado.")

    id_evaluador = None
    if rol == UserRole.PROFESOR:
        profe = db.table("profesores").select("idprofesor").eq("idusuario", id_usuario).execute()
        id_evaluador = profe.data[0]["idprofesor"]

    try:
        db.table("historial_grados").insert({
            "idalumno": datos.idalumno,
            "idgrado_anterior": id_grado_anterior,
            "idgrado_nuevo": datos.id_nuevo_grado,
            "idexamen": None,
            "fecha_examen": str(datos.fecha_promocion),
            "idprofesor_evaluador": id_evaluador,
            "notas": datos.notas
        }).execute()

        db.table("alumnos").update({"idgradoactual": datos.id_nuevo_grado}).eq("idalumno", datos.idalumno).execute()

        pago_creado = False
        if datos.monto > 0:
            pago_payload = {
                "idalumno": datos.idalumno,
                "idescuela": id_escuela,
                "id_tipo_pago": TipoPago.EXAMEN.value,
                "monto": datos.monto,
                "concepto": f"Cargo Administrativo: Cambio de Cinta ({datos.notas})",
                "id_referencia_evento": None,
                "estatus": EstatusPago.PENDIENTE.value
            }
            db.table("pagos").insert(pago_payload).execute()
            pago_creado = True

        return {
            "message": "Promoción manual procesada",
            "pago_pendiente_generado": pago_creado,
            "monto": datos.monto if pago_creado else 0
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en el proceso: {str(e)}")


@router.get("/historial/{idalumno}", response_model=List[HistorialGrado])
async def obtener_historial_completo(idalumno: int, db: Client = Depends(get_db)):
    """Obtiene la línea de tiempo de grados del alumno."""
    try:
        result = db.table("historial_grados")\
            .select("*, grado_anterior:cintasgrados!idgrado_anterior(*), grado_nuevo:cintasgrados!idgrado_nuevo(*)")\
            .eq("idalumno", idalumno)\
            .order("fecharegistro", desc=True)\
            .execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))