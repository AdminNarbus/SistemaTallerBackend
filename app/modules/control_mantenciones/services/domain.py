"""Reglas puras de fechas, kilometrajes y proyección preventiva."""

from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from statistics import median
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


MAX_KM_POR_DIA = 2000
MAX_KM_POR_SEMANA = 10000
DIAS_POR_SEMANA = 7


def motivo_aumento_excesivo(
    fecha: date | None, kilometraje: Decimal | None, anterior: dict
) -> str | None:
    fecha_anterior = anterior.get("anterior_fecha")
    km_anterior = anterior.get("anterior_km")
    if (
        fecha is None or kilometraje is None or fecha_anterior is None or km_anterior is None
    ):
        return None
    dias = (fecha - fecha_anterior).days
    if dias <= 0:
        return None
    semanas, dias_restantes = divmod(dias, DIAS_POR_SEMANA)
    limite = semanas * MAX_KM_POR_SEMANA + min(
        dias_restantes * MAX_KM_POR_DIA, MAX_KM_POR_SEMANA
    )
    if kilometraje - km_anterior <= limite:
        return None
    return "El aumento de kilometraje supera el límite posible para el período entre lecturas."


def desplazar_mes(fecha: date, meses: int) -> date:
    indice = fecha.year * 12 + fecha.month - 1 + meses
    anio, mes = divmod(indice, 12)
    return date(anio, mes + 1, min(fecha.day, monthrange(anio, mes + 1)[1]))


def ritmo_odometro(lecturas: list[tuple[date, Decimal]], referencia: Decimal) -> Decimal:
    """Estima el ritmo reciente y cambia de base solo ante un aumento sostenido."""
    recientes = lecturas[-5:]
    tramos = [
        ((actual[0] - anterior[0]).days, actual[1] - anterior[1])
        for anterior, actual in zip(recientes, recientes[1:])
    ]
    if len(tramos) < 2:
        return referencia

    ritmos = [kilometros / dias for dias, kilometros in tramos]
    ultimos_tramos = tramos[-2:]
    dias_recientes = sum(dias for dias, _ in ultimos_tramos)
    if (
        dias_recientes >= 7
        and all(3 <= dias <= 14 for dias, _ in ultimos_tramos)
        and all(ritmo >= referencia * Decimal("1.25") for ritmo in ritmos[-2:])
    ):
        ritmo_reciente = sum(km for _, km in ultimos_tramos) / dias_recientes
        if ritmo_reciente >= referencia * Decimal("1.50"):
            return ritmo_reciente

    return median(ritmos) or referencia


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
    odometro = set()
    for registro in registros:
        if registro["estado"] != "aceptado":
            continue
        fecha, kilometraje = registro["fecha"], registro["kilometraje"]
        dias.setdefault(fecha, set()).add(kilometraje)
        if registro.get("tipo") == "kilometraje" and not registro.get("interpolado"):
            odometro.add((fecha, kilometraje))
    if len(dias) < 3 or any(len(valores) != 1 for valores in dias.values()):
        return fallo
    ordenados = sorted((dia, next(iter(valores))) for dia, valores in dias.items())
    cobertura = (ordenados[-1][0] - ordenados[0][0]).days
    if cobertura < 7 or any(b[1] < a[1] for a, b in zip(ordenados, ordenados[1:])):
        return fallo
    referencia = (ordenados[-1][1] - ordenados[0][1]) / cobertura
    if referencia <= 0 or ficha["ultima_lectura"] > ordenados[-1][0]:
        return fallo
    tasa = ritmo_odometro(sorted(odometro), referencia)
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
