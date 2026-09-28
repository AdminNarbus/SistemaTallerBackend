from datetime import datetime
from typing import Any, List, Optional
from fastapi import UploadFile

from app.core.exceptions import BusinessRuleException


def calcular_duracion_minutos(inicio: Optional[datetime], fin: Optional[datetime]) -> int:
    """
    Función de Dominio Pura: Calcula la duración en minutos entre dos datetimes
    de forma segura, normalizando diferencias entre datetimes naive y aware.
    Retorna mínimo 1 minuto si transcurrió tiempo positivo, o 0 si no hay fechas.
    """
    if not inicio or not fin:
        return 0

    d_inicio = inicio.replace(tzinfo=None) if inicio.tzinfo else inicio
    d_fin = fin.replace(tzinfo=None) if fin.tzinfo else fin

    delta_seconds = max(0.0, (d_fin - d_inicio).total_seconds())
    return max(1, int(delta_seconds / 60))


def calcular_horas_en_taller(
    inicio: Optional[datetime],
    fin: Optional[datetime] = None,
) -> Optional[float]:
    """
    Función de Dominio Pura: Calcula las horas transcurridas en taller de forma segura,
    normalizando diferencias entre datetimes naive y aware (offset-naive vs offset-aware).
    Si fin es None, toma datetime.now().
    """
    if not inicio:
        return None

    d_inicio = inicio.replace(tzinfo=None) if inicio.tzinfo else inicio
    if fin:
        d_fin = fin.replace(tzinfo=None) if fin.tzinfo else fin
    else:
        d_fin = datetime.now()

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
    ref_now = now or datetime.now()
    d_ref_now = ref_now.replace(tzinfo=None) if ref_now.tzinfo else ref_now

    total_visitas = len(estadias)
    if not estadias:
        acumulado = float(horas_taller_acumuladas_db or 0.0)
        return round(acumulado, 1), 0

    horas_acumuladas = 0.0
    for est in estadias:
        if isinstance(est, dict):
            h = est.get("horas_estadia")
            f_ing = est.get("fecha_ingreso")
            f_sal = est.get("fecha_salida")
        else:
            h = getattr(est, "horas_estadia", None)
            f_ing = getattr(est, "fecha_ingreso", None)
            f_sal = getattr(est, "fecha_salida", None)

        if h is not None:
            horas_acumuladas += float(h)
        elif f_ing is not None and f_sal is None:
            # Estadía en curso actualmente
            d_ing = f_ing.replace(tzinfo=None) if hasattr(f_ing, "replace") and f_ing.tzinfo else f_ing
            if isinstance(d_ing, str):
                try:
                    d_ing = datetime.fromisoformat(d_ing)
                    d_ing = d_ing.replace(tzinfo=None) if d_ing.tzinfo else d_ing
                except Exception:
                    d_ing = None
            if d_ing:
                delta = max(0.0, (d_ref_now - d_ing).total_seconds())
                horas_acumuladas += delta / 3600.0

    return round(horas_acumuladas, 1), total_visitas


def validar_pauta_preventiva_cierre(
    total_items: int,
    items_respondidos: int,
    motivo_incompleto: Optional[str],
) -> Optional[str]:
    """
    Regla de Dominio: Verifica si la pauta preventiva se completó en su totalidad.
    Si faltan ítems por responder, exige una justificación no vacía.
    """
    if total_items > 0 and items_respondidos < total_items:
        if not (motivo_incompleto and motivo_incompleto.strip()):
            raise BusinessRuleException(
                f"La pauta preventiva está incompleta ({items_respondidos}/{total_items} ítems respondidos). "
                "Debe completar la pauta o ingresar una justificación en 'motivo_incompleto_checklist'."
            )
        return motivo_incompleto.strip()
    return motivo_incompleto.strip() if motivo_incompleto else None


def validar_fallas_cierre_parcial(
    cantidad_fallas_no_resueltas: int,
    motivo_cierre_parcial: Optional[str],
) -> Optional[str]:
    """
    Regla de Dominio: Si existen averías no resueltas o con falta de repuestos al finalizar,
    exige obligatoriamente una justificación técnica en 'motivo_cierre_parcial'.
    """
    if cantidad_fallas_no_resueltas > 0:
        if not (motivo_cierre_parcial and motivo_cierre_parcial.strip()):
            raise BusinessRuleException(
                f"Existen {cantidad_fallas_no_resueltas} falla(s) no resueltas o con falta de repuestos. "
                "Para liberar el bus con cierre parcial, debe ingresar una justificación en 'motivo_cierre_parcial'."
            )
        return motivo_cierre_parcial.strip()
    return motivo_cierre_parcial.strip() if motivo_cierre_parcial else None


def formatear_comentario_cierre(
    mecanico_nombre: str,
    liberar_bus: bool,
    comentario_cierre: Optional[str] = None,
    motivo_cierre_parcial: Optional[str] = None,
    motivo_incompleto_checklist: Optional[str] = None,
) -> str:
    """Construye el texto descriptivo canónico para la bitácora de cierre de una orden."""
    if liberar_bus:
        texto = f"{mecanico_nombre} finalizó los trabajos de la OT y liberó el bus para operaciones."
    else:
        texto = f"{mecanico_nombre} finalizó los trabajos de la OT (el bus permanece en taller)."

    if comentario_cierre and comentario_cierre.strip():
        texto += f" Comentario de cierre: {comentario_cierre.strip()}."
    if motivo_cierre_parcial:
        texto += f" Motivo cierre parcial: {motivo_cierre_parcial}."
    if motivo_incompleto_checklist:
        texto += f" Justificación pauta preventiva: {motivo_incompleto_checklist}."

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
    nom_falla = getattr(falla_obj, "nombre", None) if falla_obj else None

    nom_cat = None
    if falla_obj and hasattr(falla_obj, "__dict__"):
        cat_obj = falla_obj.__dict__.get("categoria")
        if cat_obj:
            nom_cat = getattr(cat_obj, "nombre", None)

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
