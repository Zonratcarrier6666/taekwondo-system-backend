# ============================================================
#  app/utils/matchmaking.py
#  Agrupa participantes por categoría y genera enfrentamientos
#  Categorías: Género + Cinta + Rango edad + Categoría peso
# ============================================================

from typing import Optional
import math


# ─────────────────────────────────────────────────────────────
#  RANGOS DE PESO ESTÁNDAR TAEKWONDO
# ─────────────────────────────────────────────────────────────

RANGOS_PESO = [
    (0,    30,   "Hasta 30 kg"),
    (30,   35,   "30–35 kg"),
    (35,   40,   "35–40 kg"),
    (40,   45,   "40–45 kg"),
    (45,   50,   "45–50 kg"),
    (50,   55,   "50–55 kg"),
    (55,   60,   "55–60 kg"),
    (60,   68,   "60–68 kg"),
    (68,   80,   "68–80 kg"),
    (80,   999,  "+80 kg"),
]

RANGOS_EDAD = [
    (4,  7,  "4–7 años"),
    (8,  11, "8–11 años"),
    (12, 14, "12–14 años"),
    (15, 17, "15–17 años"),
    (18, 30, "18–30 años"),
    (31, 99, "+31 años"),
]


def _cat_peso(peso: Optional[float]) -> str:
    if peso is None:
        return "Peso no registrado"
    for low, high, label in RANGOS_PESO:
        if low <= peso < high:
            return label
    return "+80 kg"


def _cat_edad(edad: int) -> str:
    for low, high, label in RANGOS_EDAD:
        if low <= edad <= high:
            return label
    return "Edad no clasificada"


def _genero_label(genero: Optional[str]) -> str:
    if genero == "M": return "Masculino"
    if genero == "F": return "Femenino"
    return "No especificado"


# ─────────────────────────────────────────────────────────────
#  FUNCIÓN PRINCIPAL
# ─────────────────────────────────────────────────────────────

def generar_matchmaking(participantes: list[dict]) -> list[dict]:
    """
    Recibe lista de participantes con campos:
        idalumno, nombres, apellidopaterno, edad, cinta,
        color_cinta, peso, genero, idescuela, nombreescuela

    Devuelve lista de categorías con sus enfrentamientos.
    """
    # Agrupar por categoría
    categorias: dict[str, list] = {}

    for p in participantes:
        genero   = _genero_label(p.get("genero"))
        cinta    = p.get("cinta", "Sin cinta")
        cat_edad = _cat_edad(int(p.get("edad") or 0))
        cat_peso = _cat_peso(p.get("peso"))

        key = f"{genero} | {cinta} | {cat_edad} | {cat_peso}"
        if key not in categorias:
            categorias[key] = []
        categorias[key].append(p)

    resultado = []

    for categoria, alumnos in sorted(categorias.items()):
        enfrentamientos = _generar_enfrentamientos(alumnos)
        resultado.append({
            "categoria":      categoria,
            "total":          len(alumnos),
            "participantes":  [_fmt_participante(a) for a in alumnos],
            "enfrentamientos": enfrentamientos,
            "bye":            len(alumnos) % 2 != 0,  # True si hay número impar
        })

    return resultado


def _fmt_participante(a: dict) -> dict:
    return {
        "idalumno":       a.get("idalumno"),
        "nombre":         f"{a.get('nombres','')} {a.get('apellidopaterno','')}".strip(),
        "edad":           a.get("edad"),
        "cinta":          a.get("cinta"),
        "color_cinta":    a.get("color_cinta"),
        "peso":           a.get("peso"),
        "genero":         a.get("genero"),
        "escuela":        a.get("nombreescuela", ""),
    }


def _generar_enfrentamientos(alumnos: list[dict]) -> list[dict]:
    """
    Genera la tabla de enfrentamientos tipo torneo de eliminación.
    Si hay número impar, el último recibe BYE (pasa directo a siguiente ronda).
    Se mezclan alumnos de la misma escuela lo más posible para evitar
    que compañeros se enfrenten en primera ronda.
    """
    if len(alumnos) < 2:
        return []

    # Separar por escuela e intercalar para evitar mismo dojo en ronda 1
    por_escuela: dict[int, list] = {}
    for a in alumnos:
        eid = a.get("idescuela", 0)
        if eid not in por_escuela:
            por_escuela[eid] = []
        por_escuela[eid].append(a)

    # Intercalar: tomar de cada escuela en round-robin
    mezclados = []
    listas = list(por_escuela.values())
    i = 0
    while any(listas):
        bucket = listas[i % len(listas)]
        if bucket:
            mezclados.append(bucket.pop(0))
        i += 1

    # Generar pares
    enfrentamientos = []
    for idx in range(0, len(mezclados) - 1, 2):
        a = mezclados[idx]
        b = mezclados[idx + 1]
        enfrentamientos.append({
            "numero":   (idx // 2) + 1,
            "alumno_a": _fmt_participante(a),
            "alumno_b": _fmt_participante(b),
        })

    # BYE si hay número impar
    if len(mezclados) % 2 != 0:
        ultimo = mezclados[-1]
        enfrentamientos.append({
            "numero":   len(enfrentamientos) + 1,
            "alumno_a": _fmt_participante(ultimo),
            "alumno_b": None,
            "bye":      True,
        })

    return enfrentamientos


# ─────────────────────────────────────────────────────────────
#  RESUMEN ESTADÍSTICO
# ─────────────────────────────────────────────────────────────

def resumen_matchmaking(matchmaking: list[dict]) -> dict:
    total_participantes  = sum(c["total"] for c in matchmaking)
    total_categorias     = len(matchmaking)
    total_enfrentamientos = sum(len(c["enfrentamientos"]) for c in matchmaking)
    cats_con_bye         = [c["categoria"] for c in matchmaking if c.get("bye")]

    return {
        "total_participantes":   total_participantes,
        "total_categorias":      total_categorias,
        "total_enfrentamientos": total_enfrentamientos,
        "categorias_con_bye":    cats_con_bye,
    }