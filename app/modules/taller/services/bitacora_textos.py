"""Textos breves de bitácora; el autor, tipo y fecha se muestran por separado."""
from typing import Iterable, Optional


def agregar_texto(texto: str, detalle: Optional[str]) -> str:
    detalle_limpio = (detalle or "").strip()
    if not detalle_limpio:
        return texto
    return f"{texto.rstrip('. ')}. {detalle_limpio}"


def unir_nombres(nombres: Iterable[str]) -> str:
    nombres_limpios = [nombre.strip() for nombre in nombres if nombre.strip()]
    if len(nombres_limpios) < 2:
        return "".join(nombres_limpios)
    return f"{', '.join(nombres_limpios[:-1])} y {nombres_limpios[-1]}"


def formatear_reparacion(falla: str, nombres: Iterable[str]) -> str:
    participantes = list(nombres)
    if not participantes:
        return f"Reparó: {falla}"
    accion = "repararon" if len(participantes) > 1 else "reparó"
    return f"{unir_nombres(participantes)} {accion}: {falla}"


def formatear_cambio_estado(anterior: str, nuevo: str) -> str:
    return f"{anterior.replace('_', ' ')} → {nuevo.replace('_', ' ')}"
