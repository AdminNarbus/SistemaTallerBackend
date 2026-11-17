"""Reglas puras de fechas, kilometrajes y proyección preventiva."""

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from zoneinfo import ZoneInfo
import re

INTERVALO_SCANIA = Decimal("50000")
INTERVALO_VOLVO = Decimal("40000")
INTERVALO_MERCEDES = Decimal("60000")
EXCEPCIONES_MERCEDES = {"354", "396"}
PASO_EJE_Y = Decimal("25000")


def hoy() -> date:
    return datetime.now(ZoneInfo("America/Santiago")).date()


def fecha_valida(valor: str | date | None) -> date | None:
    if isinstance(valor, date):
        return valor
    if not isinstance(valor, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def numero(valor: str | Decimal | None) -> Decimal | None:
    if valor is None or str(valor).strip() == "":
        return None
    try:
        resultado = Decimal(str(valor).strip())
        return resultado if resultado.is_finite() else None
    except InvalidOperation:
        return None


def intervalo(
    marca: str | None, numero_bus: str | None, excepcion: Decimal | None
) -> Decimal | None:
    if excepcion is not None:
        return excepcion
    normalizada = (marca or "").lower().strip()
    if normalizada in {"sc", "scania"}:
        return INTERVALO_SCANIA
    if normalizada == "volvo":
        return INTERVALO_VOLVO
    if normalizada in {"mb", "mercedes", "mercedes-benz", "mercedes benz"}:
        return (
            INTERVALO_VOLVO
            if numero_bus in EXCEPCIONES_MERCEDES
            else INTERVALO_MERCEDES
        )
    return None


def estado_km(restantes: Decimal | None) -> str:
    if restantes is None:
        return "Sin datos suficientes para calcular"
    if restantes < 0:
        return "Vencida"
    if restantes <= 8000:
        return "Crítica"
    return "Próxima" if restantes <= 20000 else "Al día"


def estado_mantencion(datos: dict) -> str:
    campos = ("fecha", "kilometraje", "tipo_mantencion", "certificado", "ot")
    completa = all(
        datos.get(campo) is not None and str(datos[campo]).strip() for campo in campos
    )
    return "completa" if completa else "incompleta"


def motivos_secuencia(
    fecha: date | None, km: Decimal | None, contexto: dict
) -> list[str]:
    motivos = []
    anterior, posterior = contexto.get("anterior"), contexto.get("posterior")
    if anterior and km is not None and anterior["kilometraje"] > km:
        motivos.append("El kilometraje es inferior a la lectura confirmada anterior.")
    if posterior and km is not None and posterior["kilometraje"] < km:
        motivos.append("El kilometraje es superior al siguiente registro confirmado.")
    if contexto.get("misma_fecha_distinta"):
        motivos.append("Hay kilometrajes distintos en la misma fecha.")
    return motivos


def desplazar_mes(fecha: date, meses: int) -> date:
    indice = fecha.year * 12 + fecha.month - 1 + meses
    anio, mes = divmod(indice, 12)
    return date(anio, mes + 1, min(fecha.day, monthrange(anio, mes + 1)[1]))


def proyectar(registros: list[dict], ficha: dict, ventana: int = 90) -> dict:
    fallo = {"disponible": False, "mensaje": "Sin datos suficientes para estimar"}
    if (
        ficha["conflicto"]
        or ficha["sin_lectura_reciente"]
        or ficha["restantes"] is None
    ):
        return fallo
    if ficha["restantes"] <= 0 or any(r["estado"] == "pendiente" for r in registros):
        return fallo
    dias = {}
    for registro in registros:
        if registro["estado"] != "aceptado":
            continue
        dias.setdefault(registro["fecha"], set()).add(registro["kilometraje"])
    if len(dias) < 3 or any(len(valores) != 1 for valores in dias.values()):
        return fallo
    ordenados = sorted((dia, next(iter(valores))) for dia, valores in dias.items())
    cobertura = (ordenados[-1][0] - ordenados[0][0]).days
    if cobertura < 7 or any(b[1] < a[1] for a, b in zip(ordenados, ordenados[1:])):
        return fallo
    tasa = (ordenados[-1][1] - ordenados[0][1]) / cobertura
    if tasa <= 0 or ficha["ultima_lectura"] > ordenados[-1][0]:
        return fallo
    dias_faltantes = int(
        (ficha["restantes"] / tasa).to_integral_value(rounding=ROUND_CEILING)
    )
    return {
        "disponible": True,
        "promedio_diario": tasa,
        "dias": dias_faltantes,
        "fecha": ficha["ultima_lectura"] + timedelta(days=dias_faltantes),
        "ventana_dias": ventana,
    }
