from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from datetime import date
from supabase import Client
import uuid

from app.utils.database import get_db
from app.utils.auth_utils import get_current_user
from app.schemas.torneos import Torneo, TorneoCreate, InscripcionTorneo, CategoriaTorneo, CategoriaTorneoCreate
from app.schemas.usuarios import UserRole
from app.schemas.pagos import TipoPago, EstatusPago

router = APIRouter(tags=["Torneos y Competencias"]) 

@router.post("/", response_model=Torneo, status_code=status.HTTP_201_CREATED)
async def crear_torneo(
    datos: TorneoCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Crea un nuevo torneo. Solo SuperAdmin.
    Ajustado a nombres: nombre, fecha, sede.
    """
    if current_user.get("rol") != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Permiso denegado.")

    try:
        result = db.table("torneos").insert(datos.model_dump(mode='json')).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/categorias", response_model=CategoriaTorneo, status_code=status.HTTP_201_CREATED)
async def crear_categoria_torneo(
    datos: CategoriaTorneoCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Crea una categoría vinculada a un torneo. Solo SuperAdmin."""
    if current_user.get("rol") != UserRole.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Permiso denegado.")

    try:
        result = db.table("torneo_categorias").insert(datos.model_dump(mode='json')).execute()
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/", response_model=List[Torneo])
async def listar_torneos_activos(db: Client = Depends(get_db)):
    """Retorna todos los torneos programados."""
    result = db.table("torneos").select("*").order("fecha").execute()
    return result.data

@router.get("/{idtorneo}/categorias", response_model=List[CategoriaTorneo])
async def listar_categorias_de_torneo(idtorneo: int, db: Client = Depends(get_db)):
    """Obtiene las categorías disponibles para un torneo específico."""
    result = db.table("torneo_categorias").select("*").eq("idtorneo", idtorneo).execute()
    return result.data

def calcular_edad(fecha_nacimiento: date, fecha_referencia: date) -> int:
    """Calcula la edad exacta a una fecha determinada."""
    return fecha_referencia.year - fecha_nacimiento.year - (
        (fecha_referencia.month, fecha_referencia.day) < 
        (fecha_nacimiento.month, fecha_nacimiento.day)
    )

@router.post("/{idtorneo}/inscribir", status_code=status.HTTP_200_OK)
async def inscribir_alumnos_a_torneo(
    idtorneo: int,
    datos: InscripcionTorneo,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Inscribe alumnos calculando la edad automáticamente y generando cargos.
    Basado en la tabla 'inscripciones_torneo'.
    """
    id_usuario = current_user.get("idusuario")
    rol = current_user.get("rol")

    # 1. Obtener datos del torneo (para la fecha y costo)
    torneo_res = db.table("torneos").select("*").eq("idtorneo", idtorneo).execute()
    if not torneo_res.data:
        raise HTTPException(status_code=404, detail="Torneo no encontrado.")
    
    torneo = torneo_res.data[0]
    fecha_torneo = date.fromisoformat(torneo["fecha"])
    costo = torneo.get("costo_inscripcion", 0.0)

    # 2. Identificar Profesor e Institución
    id_profesor = None
    id_escuela = None
    
    # Buscamos en la tabla profesores por el idusuario
    profe_res = db.table("profesores").select("idprofesor, idescuela").eq("idusuario", id_usuario).execute()
    if profe_res.data:
        id_profesor = profe_res.data[0]["idprofesor"]
        id_escuela = profe_res.data[0]["idescuela"]
    elif rol == UserRole.ESCUELA:
        esc_res = db.table("datosescuela").select("idescuela").eq("idusuario", id_usuario).execute()
        id_escuela = esc_res.data[0]["idescuela"]

    inscritos = 0
    errores = []

    for item in datos.inscripciones:
        try:
            # A. Obtener fecha de nacimiento del alumno
            alumno_res = db.table("alumnos").select("fechanacimiento, idescuela").eq("idalumno", item.idalumno).execute()
            if not alumno_res.data:
                errores.append(f"Alumno {item.idalumno} no existe.")
                continue
            
            f_nac = date.fromisoformat(alumno_res.data[0]["fechanacimiento"])
            edad_torneo = calcular_edad(f_nac, fecha_torneo)
            
            # Usar la escuela del alumno si el usuario no tiene una (caso SuperAdmin)
            target_escuela = id_escuela or alumno_res.data[0]["idescuela"]

            # B. Insertar en inscripciones_torneo (SINGULAR según tu tabla)
            db.table("inscripciones_torneo").insert({
                "idtorneo": idtorneo,
                "idalumno": item.idalumno,
                "idprofesor": id_profesor,
                "idcategoria": item.idcategoria,
                "peso_declarado": item.peso_declarado,
                "edad_al_momento": edad_torneo,
                "token_qr": str(uuid.uuid4())[:18],
                "estatus_pago": "Pendiente",
                "estatus_checkin": False
            }).execute()

            # C. Generar cargo financiero
            db.table("pagos").insert({
                "idalumno": item.idalumno,
                "idescuela": target_escuela,
                "id_tipo_pago": TipoPago.TORNEO.value,
                "monto": costo,
                "concepto": f"Inscripción Torneo: {torneo['nombre']}",
                "id_referencia_evento": idtorneo,
                "estatus": EstatusPago.PENDIENTE.value
            }).execute()

            inscritos += 1
        except Exception as e:
            errores.append(f"Error con alumno {item.idalumno}: {str(e)}")

    return {
        "message": f"Se procesaron {inscritos} inscripciones.",
        "detalle": errores
    }