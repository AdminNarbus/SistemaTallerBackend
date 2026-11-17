from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import UploadFile

from app.core.exceptions import BusinessRuleException


def normalizar_fecha_utc(fecha: datetime) -> datetime:
    """Legacy naive timestamps are UTC; offsets are converted before arithmetic."""
    return fecha.astimezone(timezone.utc).replace(tzinfo=None) if fecha.tzinfo else fecha


def calcular_duracion_minutos(inicio: Optional[datetime], fin: Optional[datetime]) -> int:
    """
    Función de Dominio Pura: Calcula la duración en minutos entre dos datetimes
    de forma segura, normalizando diferencias entre datetimes naive y aware.
    Retorna mínimo 1 minuto si transcurrió tiempo positivo, o 0 si no hay fechas.
    """
    if not inicio or not fin:
        return 0

    d_inicio = normalizar_fecha_utc(inicio)
    d_fin = normalizar_fecha_utc(fin)

    delta_seconds = max(0.0, (d_fin - d_inicio).total_seconds())
    return max(1, int(delta_seconds / 60))


def calcular_horas_en_taller(
    inicio: Optional[datetime],
    fin: Optional[datetime] = None,
) -> Optional[float]:
    """
    Función de Dominio Pura: Calcula las horas transcurridas en taller de forma segura,
    normalizando diferencias entre datetimes naive y aware (offset-naive vs offset-aware).
    Si fin es None, toma datetime.now(timezone.utc).
    """
    if not inicio:
        return None

    d_inicio = normalizar_fecha_utc(inicio)
    d_fin = normalizar_fecha_utc(fin or datetime.now(timezone.utc))

    delta_seconds = max(0.0, (d_fin - d_inicio).total_seconds())
    return round(delta_seconds / 3600.0, 1)


def calcular_telemetria_estadias(
    estadias: List[Any],
    horas_taller_acumuladas_db: Optional[float] = None,
    en_taller: bool = False,
    now: Optional[datetime] = None,
) -> tuple[float, int]:
    """
    Calcula el tiempo real acumulado en maestranza (sumando estadías cerradas más la abierta si el bus está en taller)
    y el conteo total de visitas.
    """
    ref_now = now or datetime.now(timezone.utc)
    if not estadias:
        return round(max(0.0, float(horas_taller_acumuladas_db or 0.0)), 1), 0
    total = 0.0
    for est in estadias:
        get = est.get if isinstance(est, dict) else lambda key: getattr(est, key, None)
        horas = get("horas_estadia")
        ingreso = _fecha_estadia(get("fecha_ingreso"))
        salida = _fecha_estadia(get("fecha_salida"))
        if horas is not None:
            total += max(0.0, float(horas))
        elif ingreso and (salida or en_taller):
            fin = normalizar_fecha_utc(salida or ref_now)
            total += max(0.0, (fin - normalizar_fecha_utc(ingreso)).total_seconds()) / 3600
    return round(total, 1), len(estadias)


def _fecha_estadia(valor: Any) -> Optional[datetime]:
    if isinstance(valor, datetime) or valor is None:
        return valor
    return datetime.fromisoformat(valor)


def calcular_horas_reales_taller(solicitud: Any, now: Optional[datetime] = None) -> float:
    """Permanencia física; nunca utiliza la fecha de creación de la solicitud."""
    get = solicitud.get if isinstance(solicitud, dict) else lambda key: getattr(solicitud, "__dict__", {}).get(key)
    estadias = get("estadias") or get("estadias_json") or []
    if isinstance(estadias, str):
        import json
        estadias = json.loads(estadias)
    estado = get("estado")
    fin = (get("fecha_liberacion") or get("fecha_cierre")) if estado == "LIBERADO" else (get("fecha_cierre") or get("fecha_liberacion"))
    if estado not in ("LIBERADO", "FINALIZADO"):
        fin = None
    activo = estado == "EN_REPARACION"
    if estadias:
        return calcular_telemetria_estadias(estadias, en_taller=activo or fin is not None, now=_fecha_estadia(fin) if not activo else now)[0]
    acumulado = get("horas_en_taller")
    if acumulado is None:
        acumulado = get("horas_taller_acumuladas")
    if acumulado is not None and float(acumulado) > 0:
        return round(float(acumulado), 1)
    ingreso = _fecha_estadia(get("fecha_primer_ingreso_taller") or get("fecha_ingreso"))
    if ingreso and (activo or fin):
        return calcular_horas_en_taller(ingreso, now if activo else _fecha_estadia(fin)) or 0.0
    return 0.0


def validar_pauta_preventiva_cierre(
    total_items: int,
    items_respondidos: int,
    motivo_incompleto: Optional[str],
) -> Optional[str]:
    """Normaliza una justificación opcional sin bloquear el cierre por pauta incompleta."""
    return motivo_incompleto.strip() if motivo_incompleto and motivo_incompleto.strip() else None


def validar_fallas_cierre_parcial(
    cantidad_fallas_no_resueltas: int,
    motivo_cierre_parcial: Optional[str],
) -> Optional[str]:
    """Normaliza una justificación opcional sin bloquear por averías pendientes."""
    return motivo_cierre_parcial.strip() if motivo_cierre_parcial and motivo_cierre_parcial.strip() else None


def formatear_comentario_cierre(
    mecanico_nombre: str,
    liberar_bus: bool,
    comentario_cierre: Optional[str] = None,
    motivo_cierre_parcial: Optional[str] = None,
    motivo_incompleto_checklist: Optional[str] = None,
) -> str:
    """Resume la salida del bus y las notas; el autor está en los metadatos."""
    from app.modules.taller.services.bitacora_textos import agregar_texto

    if liberar_bus:
        texto = "Cierre: bus liberado"
    else:
        texto = "Cierre: bus en taller"

    for nota in dict.fromkeys((comentario_cierre, motivo_cierre_parcial, motivo_incompleto_checklist)):
        texto = agregar_texto(texto, nota)

    return texto


def describir_detalle_averia(det: Any) -> str:
    """
    Retorna una descripción legible para humanos de la avería, sin exponer IDs técnicos
    ni disparar lazy loads síncronos sobre asyncpg.
    """
    if not det:
        return "Avería general"
    desc_pers = det.descripcion_personalizada.strip() if getattr(det, "descripcion_personalizada", None) else None

    falla_obj = det.__dict__.get("falla") if hasattr(det, "__dict__") else None
    nom_falla = getattr(det, "falla_nombre_snapshot", None) or (getattr(falla_obj, "nombre", None) if falla_obj else None)

    nom_cat = getattr(det, "categoria_nombre_snapshot", None)
    if falla_obj and hasattr(falla_obj, "__dict__"):
        cat_obj = falla_obj.__dict__.get("categoria")
        if cat_obj:
            nom_cat = nom_cat or getattr(cat_obj, "nombre", None)

    if nom_falla and desc_pers:
        return f"{nom_falla} ({desc_pers})"
    elif nom_falla:
        return nom_falla
    elif desc_pers:
        return desc_pers
    elif nom_cat:
        return f"Avería de {nom_cat}"
    return "Avería general"


def recopilar_archivos_fotos(
    foto: Optional[UploadFile] = None,
    fotos: Optional[List[UploadFile]] = None,
) -> List[UploadFile]:
    """Recopila y deduplica archivos de evidencia fotográfica recibidos."""
    archivos: List[UploadFile] = []
    if fotos:
        for f in fotos:
            if f and hasattr(f, "filename") and f.filename and f not in archivos:
                archivos.append(f)
    elif foto and hasattr(foto, "filename") and foto.filename:
        archivos.append(foto)
    return archivos
