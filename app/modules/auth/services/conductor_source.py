import logging

import httpx
from pydantic import TypeAdapter, ValidationError

from app.core.config import settings
from app.core.exceptions import BusinessRuleException
from app.modules.auth.dtos.conductor_sync_dto import ConductorExternoDTO

logger = logging.getLogger(__name__)
MAX_CONDUCTORES = 10000
SOURCE_TIMEOUT_SECONDS = 60


def validar_conductores(payload: object) -> list[ConductorExternoDTO]:
    try:
        conductores = TypeAdapter(list[ConductorExternoDTO]).validate_python(payload)
    except ValidationError as exc:
        raise BusinessRuleException("Respuesta de conductores inválida; no se modificaron usuarios.", status_code=502) from exc
    if not conductores or len(conductores) > MAX_CONDUCTORES:
        raise BusinessRuleException("Cantidad de conductores inválida; sincronización cancelada.", status_code=502)
    if len({conductor.rut for conductor in conductores}) != len(conductores):
        raise BusinessRuleException("La fuente contiene RUT duplicados; sincronización cancelada.", status_code=502)
    return conductores


def preparar_conductores(payload: object) -> tuple[list[ConductorExternoDTO], list[dict]]:
    """El último registro del API prevalece para cada RUT normalizado."""
    if not isinstance(payload, list) or not payload or len(payload) > MAX_CONDUCTORES:
        raise BusinessRuleException("Cantidad o formato de conductores inválido.", status_code=502)
    por_rut, ids_por_rut, incidencias = {}, {}, []
    for registro in payload:
        conductor = _validar_registro(registro)
        if conductor is None:
            incidencias.append({"id_fuente": registro.get("id"), "motivo": "inactivo_con_rut_invalido"})
            continue
        if conductor.rut in por_rut:
            incidencias.append({"id_fuente": ids_por_rut[conductor.rut],
                                "reemplazado_por": registro.get("id"), "motivo": "reemplazado_por_ultimo_registro"})
        por_rut[conductor.rut] = conductor
        ids_por_rut[conductor.rut] = registro.get("id")
    return validar_conductores(list(por_rut.values())), incidencias


def _validar_registro(registro: object) -> ConductorExternoDTO | None:
    try:
        return ConductorExternoDTO.model_validate(registro)
    except ValidationError as exc:
        solo_rut = all(error["loc"] == ("rut",) for error in exc.errors())
        if isinstance(registro, dict) and registro.get("activo") is False and solo_rut:
            return None
        raise BusinessRuleException("Registro inválido o conductor activo sin RUT válido; carga cancelada.", status_code=502) from exc


async def obtener_payload_conductores() -> object:
    try:
        async with httpx.AsyncClient(timeout=SOURCE_TIMEOUT_SECONDS) as client:
            response = await client.get(settings.CONDUCTORES_SYNC_URL)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("[CONDUCTOR-SYNC] Fallo al consultar la fuente")
        raise BusinessRuleException("No fue posible consultar los conductores.", status_code=502) from exc
    return payload


async def obtener_conductores() -> list[ConductorExternoDTO]:
    conductores, incidencias = preparar_conductores(await obtener_payload_conductores())
    logger.info("[CONDUCTOR-SYNC] Fuente preparada | ruts=%s reemplazados=%s rut_invalido=%s",
                len(conductores), sum(item["motivo"] == "reemplazado_por_ultimo_registro" for item in incidencias),
                sum(item["motivo"] == "inactivo_con_rut_invalido" for item in incidencias))
    return conductores
