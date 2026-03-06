# ============================================================
#  app/routers/pagos.py
# ============================================================

import os
import uuid
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from app.utils.database   import get_db
from app.utils.auth_utils import get_current_user
from app.utils.qr_generator import (
    generar_token_qr, generar_pdf_qr,
    enviar_qr_por_correo, enviar_confirmacion_cobro,   # ← nuevo
)
from app.schemas.pagos import (
    TipoPago, EstatusPago, CicloSemestral,
    get_ciclo_actual, alumno_debe_inscripcion,
    CrearPagoMensualidad, CrearPagoInscripcion,
    GenerarPagosMasivosMensualidad, GenerarInscripcionesSemestrales,
    RegistrarPago, RegistrarPagoLote,
    ConfigPagoAlumno, ConfigPagoAlumnoLote,
    FormularioTutor, SubirFormularioFirmado, ValidarFormulario,
    EnviarNotificacion, EnviarNotificacionLote,
    ResumenPagosAlumno, NotificacionResult,
)
from app.utils.notificaciones import (
    notificar_pago_pendiente,
    notificar_formulario_inscripcion,
    notificar_recordatorio,
    APP_URL,
)

router = APIRouter(prefix="/pagos", tags=["Pagos y Cobranza"])
ROLES_STAFF = {"Escuela", "Profesor", "SuperAdmin"}


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────

def _folio() -> str:
    return f"TKW-{uuid.uuid4().hex[:8].upper()}"

def _f(v) -> float:
    try: return float(v) if v is not None else 0.0
    except: return 0.0

def _i(v) -> int:
    try: return int(v) if v is not None else 0
    except: return 0

def _require_staff(user: dict):
    if user.get("rol") not in ROLES_STAFF:
        raise HTTPException(403, "Sin acceso")

def _get_alumno(idalumno: int, db: Client) -> dict:
    r = db.table("alumnos").select(
        "idalumno, nombres, apellidopaterno, fecharegistro, estatus, "
        "correotutor, telefonocontacto, idescuela"
    ).eq("idalumno", idalumno).execute()
    if not r.data:
        raise HTTPException(404, f"Alumno {idalumno} no encontrado")
    return r.data[0]

def _get_escuela(idescuela: int, db: Client) -> dict:
    r = db.table("datosescuela").select("idescuela, nombreescuela, config_json")\
        .eq("idescuela", idescuela).execute()
    if not r.data:
        raise HTTPException(404, "Escuela no encontrada")
    return r.data[0]

def _cfg_alumno(idalumno: int, idescuela: int, db: Client) -> dict:
    """Lee config individual del alumno desde datosescuela.config_json."""
    esc = _get_escuela(idescuela, db)
    return (esc.get("config_json") or {}).get(f"pago_alumno_{idalumno}", {})

def _save_cfg_alumno(idalumno: int, idescuela: int, cfg: dict, db: Client):
    esc    = _get_escuela(idescuela, db)
    cjson  = esc.get("config_json") or {}
    cjson[f"pago_alumno_{idalumno}"] = cfg
    db.table("datosescuela").update({"config_json": cjson}).eq("idescuela", idescuela).execute()

def _ya_mensualidad(idalumno: int, mes: str, db: Client) -> bool:
    r = db.table("pagos").select("idpago").eq("idalumno", idalumno)\
        .eq("id_tipo_pago", int(TipoPago.MENSUALIDAD)).like("concepto", f"%{mes}%").execute()
    return bool(r.data)

def _ya_inscripcion(idalumno: int, ciclo: str, year: int, db: Client) -> bool:
    r = db.table("pagos").select("idpago").eq("idalumno", idalumno)\
        .eq("id_tipo_pago", int(TipoPago.INSCRIPCION))\
        .like("concepto", f"%{ciclo}%").like("concepto", f"%{year}%").execute()
    return bool(r.data)

def _link_form(idalumno: int, idpago: int) -> str:
    return f"{APP_URL}/formulario/{idalumno}/{idpago}"

def _require_staff(user: dict):
    """Verifica que el usuario tenga permisos administrativos."""
    if user.get("rol") not in ROLES_STAFF:
        raise HTTPException(403, "Sin acceso")

def _calcular_edad(fecha_nac: str) -> int:
    """
    Calcula la edad actual a partir de una fecha de nacimiento.
    Útil para la credencial del torneo.
    """
    try:
        # Extraemos solo YYYY-MM-DD en caso de que venga con timestamp
        fn = date.fromisoformat(str(fecha_nac)[:10])
        hoy = date.today()
        # Restamos años y ajustamos si aún no cumple años en el año actual
        return hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
    except Exception:
        return 0
    
    
# ─────────────────────────────────────────────────────────────
#  1. CONFIG POR ALUMNO
# ─────────────────────────────────────────────────────────────

@router.post("/config/alumno")
async def set_config_alumno(
    body: ConfigPagoAlumno,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    alumno = _get_alumno(body.idalumno, db)
    cfg = {
        "monto_mensualidad": body.monto_mensualidad,
        "dia_cobro":         body.dia_cobro,
        "monto_inscripcion": body.monto_inscripcion,
        "actualizado_en":    datetime.now().isoformat(),
    }
    _save_cfg_alumno(body.idalumno, alumno["idescuela"], cfg, db)
    return {"ok": True, "idalumno": body.idalumno, "config": cfg}


@router.post("/config/alumno/lote")
async def set_config_alumno_lote(
    body: ConfigPagoAlumnoLote,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    res = []
    for c in body.configs:
        alumno = _get_alumno(c.idalumno, db)
        cfg = {
            "monto_mensualidad": c.monto_mensualidad,
            "dia_cobro":         c.dia_cobro,
            "monto_inscripcion": c.monto_inscripcion,
            "actualizado_en":    datetime.now().isoformat(),
        }
        _save_cfg_alumno(c.idalumno, alumno["idescuela"], cfg, db)
        res.append({"idalumno": c.idalumno, "ok": True})
    return {"ok": True, "total": len(res), "resultados": res}


@router.get("/config/alumno/{idalumno}")
async def get_config_alumno(
    idalumno: int,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    alumno = _get_alumno(idalumno, db)
    return {"idalumno": idalumno, "config": _cfg_alumno(idalumno, alumno["idescuela"], db)}


# ─────────────────────────────────────────────────────────────
#  2. MENSUALIDADES
# ─────────────────────────────────────────────────────────────

@router.post("/mensualidad/individual")
async def crear_mensualidad(
    body: CrearPagoMensualidad,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    alumno = _get_alumno(body.idalumno, db)
    if alumno["estatus"] != 1:
        raise HTTPException(400, "Alumno inactivo")
    if _ya_mensualidad(body.idalumno, body.mes_correspondiente, db):
        raise HTTPException(409, f"Ya existe mensualidad {body.mes_correspondiente}")

    cfg       = _cfg_alumno(body.idalumno, alumno["idescuela"], db)
    dia_cobro = cfg.get("dia_cobro", 1)
    try:
        y, m      = map(int, body.mes_correspondiente.split("-"))
        f_cobro   = str(date(y, m, min(dia_cobro, 28)))
    except Exception:
        f_cobro   = str(date.today())

    pago = {
        "idalumno":     body.idalumno,
        "idescuela":    alumno["idescuela"],
        "id_tipo_pago": int(TipoPago.MENSUALIDAD),
        "monto":        body.monto,
        "concepto":     f"Mensualidad {body.mes_correspondiente}",
        "folio_recibo": _folio(),
        "estatus":      int(EstatusPago.PENDIENTE),
        "fecha_pago":   f_cobro,
        "notas_adicionales": body.notas_adicionales,
        "desglose_interno": {
            "tipo": "mensualidad",
            "mes":  body.mes_correspondiente,
            "dia_cobro": dia_cobro,
        },
    }
    r = db.table("pagos").insert(pago).execute()
    return {"ok": True, "pago": r.data[0] if r.data else pago}


@router.post("/mensualidad/masivo")
async def mensualidades_masivo(
    body: GenerarPagosMasivosMensualidad,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    alumnos = db.table("alumnos").select("idalumno")\
        .eq("idescuela", body.idescuela).eq("estatus", 1).execute().data

    generados, omitidos, errores = [], [], []
    for al in alumnos:
        aid = al["idalumno"]
        try:
            if not body.sobrescribir_existentes and _ya_mensualidad(aid, body.mes_correspondiente, db):
                omitidos.append(aid); continue

            cfg       = _cfg_alumno(aid, body.idescuela, db)
            monto     = cfg.get("monto_mensualidad", body.monto_default)
            dia_cobro = cfg.get("dia_cobro", body.dia_cobro_default)
            y, m      = map(int, body.mes_correspondiente.split("-"))
            f_cobro   = str(date(y, m, min(dia_cobro, 28)))

            db.table("pagos").insert({
                "idalumno":     aid,
                "idescuela":    body.idescuela,
                "id_tipo_pago": int(TipoPago.MENSUALIDAD),
                "monto":        monto,
                "concepto":     f"Mensualidad {body.mes_correspondiente}",
                "folio_recibo": _folio(),
                "estatus":      int(EstatusPago.PENDIENTE),
                "fecha_pago":   f_cobro,
                "desglose_interno": {
                    "tipo": "mensualidad",
                    "mes":  body.mes_correspondiente,
                    "dia_cobro": dia_cobro,
                },
            }).execute()
            generados.append(aid)
        except Exception as e:
            errores.append({"idalumno": aid, "error": str(e)})

    return {
        "ok": True, "mes": body.mes_correspondiente,
        "generados": len(generados), "omitidos": len(omitidos), "errores": errores,
    }


# ─────────────────────────────────────────────────────────────
#  3. INSCRIPCIONES SEMESTRALES
# ─────────────────────────────────────────────────────────────

@router.post("/inscripcion/individual")
async def crear_inscripcion(
    body: CrearPagoInscripcion,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    alumno = _get_alumno(body.idalumno, db)
    if alumno["estatus"] != 1:
        raise HTTPException(400, "Alumno inactivo")

    fecha_reg = date.fromisoformat(str(alumno["fecharegistro"])[:10])
    if not alumno_debe_inscripcion(fecha_reg):
        raise HTTPException(400,
            "El alumno se registró en el ciclo actual. "
            "La inscripción se cobra al inicio del siguiente ciclo."
        )
    if _ya_inscripcion(body.idalumno, body.ciclo.value, body.year, db):
        raise HTTPException(409, f"Ya existe inscripción {body.ciclo.value} {body.year}")

    pago = {
        "idalumno":     body.idalumno,
        "idescuela":    alumno["idescuela"],
        "id_tipo_pago": int(TipoPago.INSCRIPCION),
        "monto":        body.monto,
        "concepto":     f"Inscripción {body.ciclo.value} {body.year}",
        "folio_recibo": _folio(),
        "estatus":      int(EstatusPago.PENDIENTE),
        "notas_adicionales": body.notas_adicionales,
        "desglose_interno": {
            "tipo":              "inscripcion",
            "ciclo":             body.ciclo.value,
            "year":              body.year,
            "formulario_status": "PENDIENTE",
            "firma_url":         None,
        },
    }
    r = db.table("pagos").insert(pago).execute()
    return {"ok": True, "pago": r.data[0] if r.data else pago}


@router.post("/inscripcion/masivo")
async def inscripciones_masivo(
    body: GenerarInscripcionesSemestrales,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    alumnos = db.table("alumnos").select("idalumno, fecharegistro")\
        .eq("idescuela", body.idescuela).eq("estatus", 1).execute().data

    generados, omit_ciclo, omit_exist, errores = [], [], [], []
    for al in alumnos:
        aid = al["idalumno"]
        try:
            fecha_reg = date.fromisoformat(str(al["fecharegistro"])[:10])
            if not alumno_debe_inscripcion(fecha_reg):
                omit_ciclo.append(aid); continue
            if not body.sobrescribir_existentes and _ya_inscripcion(aid, body.ciclo.value, body.year, db):
                omit_exist.append(aid); continue

            db.table("pagos").insert({
                "idalumno":     aid,
                "idescuela":    body.idescuela,
                "id_tipo_pago": int(TipoPago.INSCRIPCION),
                "monto":        body.monto,
                "concepto":     f"Inscripción {body.ciclo.value} {body.year}",
                "folio_recibo": _folio(),
                "estatus":      int(EstatusPago.PENDIENTE),
                "desglose_interno": {
                    "tipo":              "inscripcion",
                    "ciclo":             body.ciclo.value,
                    "year":              body.year,
                    "formulario_status": "PENDIENTE",
                    "firma_url":         None,
                },
            }).execute()
            generados.append(aid)
        except Exception as e:
            errores.append({"idalumno": aid, "error": str(e)})

    return {
        "ok": True, "ciclo": body.ciclo.value, "year": body.year,
        "generados":         len(generados),
        "omitidos_ciclo_reg": len(omit_ciclo),
        "omitidos_existente": len(omit_exist),
        "errores":           errores,
    }


# ─────────────────────────────────────────────────────────────
#  4. COBRAR
# ─────────────────────────────────────────────────────────────

@router.post("/cobrar", summary="Registrar pago y enviar confirmación por correo")
async def cobrar_pago(
    body: RegistrarPago,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Cambia el estatus de un pago a PAGADO.
    - Tipo TORNEO (4): genera QR + PDF y envía al tutor.
    - Cualquier otro tipo: envía confirmación de cobro al tutor.
    Ambos usan Resend (no SMTP).
    """
    _require_staff(user)

    # 1. Obtener datos del pago
    p_res = db.table("pagos").select("*").eq("idpago", body.idpago).execute()
    if not p_res.data:
        raise HTTPException(404, "No se encontró el registro de pago")
    pago = p_res.data[0]

    # 2. Marcar como PAGADO
    db.table("pagos").update({
        "estatus":           int(EstatusPago.PAGADO),
        "metodo_pago":       body.metodo_pago.value,
        "fecha_pago":        datetime.now().isoformat(),
        "url_comprobante":   body.url_comprobante,
        "notas_adicionales": body.notas,
    }).eq("idpago", body.idpago).execute()

    # 3. Datos compartidos: alumno y escuela
    al_res  = db.table("alumnos").select("*")\
                .eq("idalumno", pago["idalumno"]).execute()
    esc_res = db.table("datosescuela").select("nombreescuela")\
                .eq("idescuela", pago.get("idescuela", 0)).execute()

    correo_tutor   = None
    nombre_alumno  = "Alumno"
    nombre_escuela = "Dragon Negro Dojo"

    if al_res.data:
        al            = al_res.data[0]
        correo_tutor  = al.get("correotutor")
        nombre_alumno = f"{al['nombres']} {al['apellidopaterno']}"
    if esc_res.data:
        nombre_escuela = esc_res.data[0].get("nombreescuela", nombre_escuela)

    # 4a. TORNEO → QR + PDF
    if pago.get("id_tipo_pago") == int(TipoPago.TORNEO):
        desglose      = pago.get("desglose_interno") or {}
        idinscripcion = desglose.get("idinscripcion")
        idtorneo      = desglose.get("idtorneo")

        if idinscripcion and idtorneo and al_res.data:
            token_qr = generar_token_qr()
            db.table("inscripciones_torneo").update({
                "estatus_pago": "pagado",
                "token_qr":     token_qr,
            }).eq("idinscripcion", idinscripcion).execute()

            t_res = db.table("torneos").select("*")\
                      .eq("idtorneo", idtorneo).execute()
            if t_res.data:
                torneo = t_res.data[0]
                try:
                    pdf_bytes = generar_pdf_qr(
                        token         = token_qr,
                        nombre_alumno = nombre_alumno,
                        nombre_torneo = torneo["nombre"],
                        fecha_torneo  = torneo["fecha"],
                        hora_torneo   = torneo.get("hora_inicio", "09:00"),
                        sede_torneo   = torneo["sede"],
                        ciudad_torneo = torneo["ciudad"],
                        cinta         = "Confirmada",
                        edad          = _calcular_edad(al.get("fechanacimiento", "")),
                        peso          = al.get("peso"),
                    )
                    if correo_tutor:
                        enviar_qr_por_correo(
                            token         = token_qr,
                            correo_tutor  = correo_tutor,
                            nombre_alumno = nombre_alumno,
                            nombre_torneo = torneo["nombre"],
                            fecha_torneo  = torneo["fecha"],
                            hora_torneo   = torneo.get("hora_inicio", "09:00"),
                            sede_torneo   = torneo["sede"],
                            ciudad_torneo = torneo["ciudad"],
                            pdf_bytes     = pdf_bytes,
                            from_name     = nombre_escuela,
                        )
                except Exception as e:
                    # El cobro ya quedó guardado — no revertir por error de email
                    print(f"[ERROR QR/PDF] idpago={body.idpago}: {e}")

    # 4b. MENSUALIDAD / INSCRIPCIÓN / EXAMEN / OTRO → confirmación simple
    else:
        if correo_tutor:
            try:
                enviar_confirmacion_cobro(
                    correo_tutor  = correo_tutor,
                    nombre_alumno = nombre_alumno,
                    concepto      = pago.get("concepto", "Pago"),
                    monto         = float(pago.get("monto") or 0),
                    metodo_pago   = body.metodo_pago.value,
                    folio         = pago.get("folio_recibo", ""),
                    nombre_escuela = nombre_escuela,
                )
            except Exception as e:
                print(f"[ERROR EMAIL COBRO] idpago={body.idpago}: {e}")
        else:
            print(f"[COBRO] idpago={body.idpago} — alumno sin correotutor, no se envió email")

    return {"ok": True, "mensaje": "Cobro registrado y QR enviado al correo"}


@router.post("/cobrar/lote")
async def cobrar_lote(
    body: RegistrarPagoLote,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    for idpago in body.idpagos:
        db.table("pagos").update({
            "estatus":     int(EstatusPago.PAGADO),
            "metodo_pago": body.metodo_pago.value,
            "fecha_pago":  datetime.now().isoformat(),
            "notas_adicionales": body.notas,
        }).eq("idpago", idpago).execute()
    return {"ok": True, "cobrados": len(body.idpagos)}


# ─────────────────────────────────────────────────────────────
#  5. FORMULARIO TUTOR
# ─────────────────────────────────────────────────────────────

@router.post("/formulario/guardar")
async def guardar_formulario(
    body: FormularioTutor,
    db: Client = Depends(get_db),
):
    """Endpoint público — el tutor llena el formulario desde el link enviado."""
    upd_al: dict = {}
    if body.tipo_sangre:               upd_al["tipo_sangre"]   = body.tipo_sangre
    if body.alergias:                  upd_al["alergias"]      = body.alergias
    if body.padecimientos:             upd_al["padecimientos_cronicos"] = body.padecimientos
    if body.seguro_medico:             upd_al["seguro_medico"] = body.seguro_medico
    if body.contacto_emergencia_nombre: upd_al["contacto_emergencia_nombre"] = body.contacto_emergencia_nombre
    if body.contacto_emergencia_tel:   upd_al["contacto_emergencia_tel"]    = body.contacto_emergencia_tel
    if body.correo_tutor:              upd_al["correotutor"]       = body.correo_tutor
    if body.telefono_tutor:            upd_al["telefonocontacto"]  = body.telefono_tutor
    if body.nombre_tutor:              upd_al["nombretutor"]       = body.nombre_tutor
    if upd_al:
        db.table("alumnos").update(upd_al).eq("idalumno", body.idalumno).execute()

    # Actualizar desglose del pago de inscripción correspondiente
    pagos = db.table("pagos").select("idpago, desglose_interno")\
        .eq("idalumno", body.idalumno)\
        .eq("id_tipo_pago", int(TipoPago.INSCRIPCION)).execute().data or []

    for p in pagos:
        d = p.get("desglose_interno") or {}
        if d.get("ciclo") == body.ciclo.value and str(d.get("year", "")) == str(body.year):
            d["formulario_status"] = "SUBIDO_SIN_FIRMA"
            d["formulario_datos"]  = {
                "nombre_tutor":      body.nombre_tutor,
                "curp_tutor":        body.curp_tutor,
                "direccion":         body.direccion_tutor,
                "acepta_reglamento": body.acepta_reglamento,
                "autoriza_imagen":   body.autoriza_uso_imagen,
                "llenado_en":        datetime.now().isoformat(),
            }
            db.table("pagos").update({"desglose_interno": d}).eq("idpago", p["idpago"]).execute()

    return {"ok": True, "mensaje": "Formulario guardado. Ahora sube el formulario firmado."}


@router.post("/formulario/firma/subir")
async def subir_firma(
    body: SubirFormularioFirmado,
    db: Client = Depends(get_db),
):
    """Endpoint público — el tutor sube la foto del formulario firmado."""
    r = db.table("pagos").select("idpago, desglose_interno")\
        .eq("idpago", body.idpago).execute()
    if not r.data:
        raise HTTPException(404, "Pago no encontrado")

    d = r.data[0].get("desglose_interno") or {}
    d["formulario_status"] = "FIRMADO_PENDIENTE_VALIDACION"
    d["firma_url"]         = body.firma_url
    d["firma_subida_en"]   = datetime.now().isoformat()

    db.table("pagos").update({
        "desglose_interno": d,
        "url_comprobante":  body.firma_url,
        "notas_adicionales": body.notas,
    }).eq("idpago", body.idpago).execute()
    return {"ok": True, "mensaje": "Formulario firmado recibido. Pendiente de validación."}


@router.post("/formulario/validar")
async def validar_formulario(
    body: ValidarFormulario,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    r = db.table("pagos").select("idpago, desglose_interno")\
        .eq("idpago", body.idpago).execute()
    if not r.data:
        raise HTTPException(404, "Pago no encontrado")

    d = r.data[0].get("desglose_interno") or {}
    if body.aprobado:
        d["formulario_status"] = "VALIDADO"
        d["validado_en"]       = datetime.now().isoformat()
        d["validado_por"]      = user.get("idusuario")
    else:
        d["formulario_status"] = "RECHAZADO"
        d["motivo_rechazo"]    = body.motivo_rechazo
        d["rechazado_en"]      = datetime.now().isoformat()

    db.table("pagos").update({"desglose_interno": d}).eq("idpago", body.idpago).execute()
    return {"ok": True, "estatus": d["formulario_status"]}


# ─────────────────────────────────────────────────────────────
#  6. NOTIFICACIONES
# ─────────────────────────────────────────────────────────────

@router.post("/notificar", response_model=NotificacionResult)
async def notificar(
    body: EnviarNotificacion,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    alumno  = _get_alumno(body.idalumno, db)
    escuela = _get_escuela(alumno["idescuela"], db)
    correo  = alumno.get("correotutor")
    tel     = alumno.get("telefonocontacto")
    nombre  = f"{alumno['nombres']} {alumno['apellidopaterno']}"

    if not correo and not tel:
        raise HTTPException(400, "Sin correo ni teléfono del tutor. Actualiza los datos del alumno.")

    if body.tipo == "formulario":
        # Buscar el pago de inscripción pendiente más reciente
        pago_insc = db.table("pagos").select("idpago").eq("idalumno", body.idalumno)\
            .eq("id_tipo_pago", int(TipoPago.INSCRIPCION))\
            .eq("estatus", int(EstatusPago.PENDIENTE))\
            .order("fecharegistro", desc=True).limit(1).execute()
        idpago = body.idpago or (pago_insc.data[0]["idpago"] if pago_insc.data else 0)
        link   = _link_form(body.idalumno, idpago)
        result = notificar_formulario_inscripcion(
            correo, nombre, escuela["nombreescuela"],
            get_ciclo_actual().value, link,
        )
    else:
        if body.idpago:
            p = db.table("pagos").select("*").eq("idpago", body.idpago).execute().data
        else:
            p = db.table("pagos").select("*").eq("idalumno", body.idalumno)\
                .eq("estatus", int(EstatusPago.PENDIENTE))\
                .order("fecharegistro", desc=True).limit(1).execute().data
        if not p:
            raise HTTPException(404, "Sin pagos pendientes para este alumno")
        pago   = p[0]
        result = notificar_pago_pendiente(
            correo, nombre, escuela["nombreescuela"],
            pago.get("concepto", "Pago pendiente"),
            _f(pago.get("monto")),
            pago.get("folio_recibo", ""),
            str(pago.get("fecha_pago", ""))[:10],
        )

    return NotificacionResult(
        idalumno=body.idalumno,
        email_ok=result["email"],
        error=result["error"],
    )


@router.post("/notificar/lote")
async def notificar_lote(
    body: EnviarNotificacionLote,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    resultados = []
    for aid in body.idalumnos:
        try:
            alumno  = _get_alumno(aid, db)
            escuela = _get_escuela(alumno["idescuela"], db)
            correo  = alumno.get("correotutor")
            tel     = alumno.get("telefonocontacto")
            nombre  = f"{alumno['nombres']} {alumno['apellidopaterno']}"

            if not correo and not tel:
                resultados.append({"idalumno": aid, "error": "Sin contacto"}); continue

            p = db.table("pagos").select("*").eq("idalumno", aid)\
                .eq("estatus", int(EstatusPago.PENDIENTE))\
                .order("fecharegistro", desc=True).limit(1).execute().data
            if not p:
                resultados.append({"idalumno": aid, "error": "Sin pagos pendientes"}); continue

            pago   = p[0]
            result = notificar_pago_pendiente(
                correo, nombre, escuela["nombreescuela"],
                pago.get("concepto", ""), _f(pago.get("monto")),
                pago.get("folio_recibo", ""),
                str(pago.get("fecha_pago", ""))[:10],
                body.canal,
            )
            resultados.append({
                "idalumno":          aid,
                "email_ok": result["email"],
                "error":             result["error"],
            })
        except Exception as e:
            resultados.append({"idalumno": aid, "error": str(e)})

    return {"ok": True, "total": len(resultados), "resultados": resultados}


# ─────────────────────────────────────────────────────────────
#  7. CONSULTAS
# ─────────────────────────────────────────────────────────────

@router.get("/alumno/{idalumno}/resumen", response_model=ResumenPagosAlumno)
async def resumen_alumno(
    idalumno: int,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    alumno = _get_alumno(idalumno, db)
    cfg    = _cfg_alumno(idalumno, alumno["idescuela"], db)
    pagos  = db.table("pagos").select("*").eq("idalumno", idalumno).execute().data or []

    mens_pag  = sum(1 for p in pagos if p["id_tipo_pago"] == int(TipoPago.MENSUALIDAD) and p["estatus"] == int(EstatusPago.PAGADO))
    mens_pend = sum(1 for p in pagos if p["id_tipo_pago"] == int(TipoPago.MENSUALIDAD) and p["estatus"] == int(EstatusPago.PENDIENTE))
    adeudo    = sum(_f(p["monto"]) for p in pagos if p["estatus"] == int(EstatusPago.PENDIENTE))

    ciclo_act = get_ciclo_actual()
    insc = next((
        p for p in pagos
        if p["id_tipo_pago"] == int(TipoPago.INSCRIPCION)
        and ciclo_act.value in (p.get("concepto") or "")
    ), None)

    if insc:
        d = insc.get("desglose_interno") or {}
        form_status = d.get("formulario_status", "PENDIENTE")
        insc_status = "PAGADA" if insc["estatus"] == int(EstatusPago.PAGADO) else "PENDIENTE"
    else:
        insc_status = "NO_APLICA"
        form_status = None

    return ResumenPagosAlumno(
        idalumno=idalumno,
        nombres=alumno["nombres"],
        apellidopaterno=alumno["apellidopaterno"],
        mensualidades_pagadas=mens_pag,
        mensualidades_pendientes=mens_pend,
        inscripcion_ciclo_actual=insc_status,
        formulario_status=form_status,
        total_adeudo=round(adeudo, 2),
        dia_cobro=cfg.get("dia_cobro", 1),
        monto_mensualidad=cfg.get("monto_mensualidad", 0.0),
    )


@router.get("/escuela/{idescuela}/pendientes")
async def pendientes_escuela(
    idescuela: int,
    tipo: Optional[int] = Query(None, description="1=Mensualidad 2=Inscripción"),
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    q = db.table("pagos").select(
        "idpago, idalumno, concepto, monto, folio_recibo, fecha_pago, "
        "id_tipo_pago, desglose_interno, "
        "alumnos(nombres, apellidopaterno, correotutor, telefonocontacto)"
    ).eq("idescuela", idescuela).eq("estatus", int(EstatusPago.PENDIENTE))
    if tipo:
        q = q.eq("id_tipo_pago", tipo)
    r = q.order("fecha_pago").execute()
    return {"ok": True, "total": len(r.data), "pagos": r.data}


@router.get("/formularios/pendientes/{idescuela}")
async def formularios_pendientes(
    idescuela: int,
    user: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    _require_staff(user)
    r = db.table("pagos").select(
        "idpago, idalumno, concepto, desglose_interno, url_comprobante, "
        "alumnos(nombres, apellidopaterno)"
    ).eq("idescuela", idescuela)\
     .eq("id_tipo_pago", int(TipoPago.INSCRIPCION))\
     .not_.is_("url_comprobante", "null").execute()

    pendientes = [
        p for p in r.data
        if (p.get("desglose_interno") or {}).get("formulario_status")
        in ("FIRMADO_PENDIENTE_VALIDACION", "RECHAZADO")
    ]
    return {"ok": True, "total": len(pendientes), "formularios": pendientes}

# ─────────────────────────────────────────────────────────────
#  HISTORIAL COMPLETO DE PAGOS POR ESCUELA
#  GET /finanzas/pagos/escuela/{idescuela}/historial
# ─────────────────────────────────────────────────────────────

@router.get("/escuela/{idescuela}/historial")
async def historial_pagos(
    idescuela:    int,
    # ── Filtros ──────────────────────────────────────────
    estatus:      Optional[int]  = Query(None, description="0=Pendiente 1=Pagado"),
    id_tipo_pago: Optional[int]  = Query(None, description="1=Mensualidad 2=Inscripcion 3=Otro 4=Torneo"),
    metodo_pago:  Optional[str]  = Query(None, description="Efectivo|Transferencia|Tarjeta"),
    idalumno:     Optional[int]  = Query(None),
    buscar:       Optional[str]  = Query(None, description="Nombre del alumno o concepto"),
    fecha_desde:  Optional[str]  = Query(None, description="YYYY-MM-DD"),
    fecha_hasta:  Optional[str]  = Query(None, description="YYYY-MM-DD"),
    # ── Paginación ───────────────────────────────────────
    pagina:       int            = Query(1,  ge=1),
    por_pagina:   int            = Query(20, ge=1, le=100),
    # ── Auth ─────────────────────────────────────────────
    user: dict   = Depends(get_current_user),
    db: Client   = Depends(get_db),
):
    _require_staff(user)

    q = db.table("pagos").select(
        "idpago, idalumno, idescuela, concepto, monto, estatus, "
        "id_tipo_pago, metodo_pago, folio_recibo, "
        "fecha_pago, fecharegistro, notas_adicionales, url_comprobante, "
        "alumnos(nombres, apellidopaterno)"
    ).eq("idescuela", idescuela)

    # ── Aplicar filtros ──────────────────────────────────
    if estatus is not None:
        q = q.eq("estatus", estatus)
    if id_tipo_pago is not None:
        q = q.eq("id_tipo_pago", id_tipo_pago)
    if metodo_pago:
        q = q.eq("metodo_pago", metodo_pago)
    if idalumno:
        q = q.eq("idalumno", idalumno)
    if fecha_desde:
        q = q.gte("fecharegistro", fecha_desde)
    if fecha_hasta:
        # incluir todo el día hasta
        q = q.lte("fecharegistro", f"{fecha_hasta}T23:59:59")

    q = q.order("fecharegistro", desc=True)
    r = q.execute()
    todos = r.data or []

    # ── Búsqueda por nombre/concepto (post-filter) ───────
    if buscar:
        buscar_lower = buscar.lower()
        todos = [
            p for p in todos
            if buscar_lower in (p.get("concepto") or "").lower()
            or buscar_lower in f"{(p.get('alumnos') or {}).get('nombres', '')} {(p.get('alumnos') or {}).get('apellidopaterno', '')}".lower()
        ]

    # ── Totales (antes de paginar) ───────────────────────
    total          = len(todos)
    total_monto    = sum(float(p.get("monto") or 0) for p in todos)
    total_pagados  = sum(1 for p in todos if p.get("estatus") == int(EstatusPago.PAGADO))
    total_pendientes = sum(1 for p in todos if p.get("estatus") == int(EstatusPago.PENDIENTE))

    # ── Paginación ───────────────────────────────────────
    offset = (pagina - 1) * por_pagina
    pagina_data = todos[offset : offset + por_pagina]

    return {
        "ok":               True,
        "total":            total,
        "total_monto":      round(total_monto, 2),
        "total_pagados":    total_pagados,
        "total_pendientes": total_pendientes,
        "pagina":           pagina,
        "por_pagina":       por_pagina,
        "paginas":          max(1, -(-total // por_pagina)),  # ceil division
        "pagos":            pagina_data,
    }