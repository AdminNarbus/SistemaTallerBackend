"""Sincronización de conductores en Neon. Revisión por defecto; --aplicar confirma.

Ejecutar desde la raíz: python -m scripts.incorporar_conductores_neon --help
La conexión se toma de NEON_DATABASE_URL o de --conexion-desde (AST, sin ejecutar).
"""
import argparse
import ast
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import BusinessRuleException
from app.modules.auth.dtos.conductor_sync_dto import ConductorExternoDTO
from app.modules.auth.services.conductor_source import obtener_payload_conductores, preparar_conductores
from app.modules.auth.services.conductor_sync_service import conductor_sync_service

logger = logging.getLogger(__name__)
CONNECTION_TIMEOUT_SECONDS = 20


class OpcionesCarga(BaseModel):
    aplicar: bool = False
    solo_nuevos: bool = False
    conexion_desde: Path | None = None
    informe: Path = Field(default=Path(".tmp/informe_sincronizacion_conductores_neon.json"))


def leer_conexion_legada(path: Path) -> str:
    """Lee únicamente constantes PostgreSQL, sin importar ni ejecutar el script legado."""
    arbol = ast.parse(path.read_text(encoding="utf-8-sig"))
    conexiones = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            if nodo.value.startswith(("postgresql://", "postgresql+asyncpg://")):
                url = make_url(nodo.value)
                if url.host and url.host.endswith(".neon.tech") and url.database == "taller":
                    conexiones.add(nodo.value)
    if len(conexiones) != 1:
        raise BusinessRuleException("El archivo debe contener una única conexión a taller en Neon.")
    return conexiones.pop()


def resolver_conexion(opciones: OpcionesCarga) -> URL:
    raw = os.getenv("NEON_DATABASE_URL")
    if not raw and opciones.conexion_desde:
        raw = leer_conexion_legada(opciones.conexion_desde)
    if not raw:
        raise BusinessRuleException("Configura NEON_DATABASE_URL o indica --conexion-desde ARCHIVO.")
    url = make_url(raw)
    if not url.host or not url.host.endswith(".neon.tech") or url.database != "taller":
        raise BusinessRuleException("La carga permite únicamente la base taller en Neon.")
    query = {key: value for key, value in url.query.items() if key not in ("sslmode", "channel_binding", "ssl")}
    return url.set(drivername="postgresql+asyncpg", query={**query, "ssl": "require"})


def guardar_informe(path: Path, contenido: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")


def preparar_carga(payload: object) -> tuple[list[ConductorExternoDTO], list[dict]]:
    return preparar_conductores(payload)


async def ejecutar(opciones: OpcionesCarga) -> dict:
    url = resolver_conexion(opciones)
    conductores, incidencias = preparar_carga(await obtener_payload_conductores())
    logger.info("Fuente: ruts=%s | reemplazados=%s | rut_invalido=%s", len(conductores),
                sum(item["motivo"] == "reemplazado_por_ultimo_registro" for item in incidencias),
                sum(item["motivo"] == "inactivo_con_rut_invalido" for item in incidencias))
    logger.info("Destino: host=%s base=%s | modo=%s", url.host, url.database,
                "aplicar" if opciones.aplicar else "revision")
    engine = create_async_engine(url, hide_parameters=True, connect_args={"timeout": CONNECTION_TIMEOUT_SECONDS})
    try:
        sesiones = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        async with sesiones() as db:
            if opciones.solo_nuevos:
                accion = (conductor_sync_service.incorporar_nuevos if opciones.aplicar
                          else conductor_sync_service.previsualizar_altas)
            else:
                accion = (conductor_sync_service.sincronizar_ahora if opciones.aplicar
                          else conductor_sync_service.previsualizar_sincronizacion)
            resultado = await accion(db, conductores)
            if not opciones.aplicar:
                await db.rollback()
    finally:
        await engine.dispose()
    informe = {"fecha_utc": datetime.now(timezone.utc).isoformat(),
               "modo": "aplicado" if opciones.aplicar else "revision_sin_cambios",
               "host": url.host, "base": url.database, **resultado.model_dump(),
               "alcance": "solo_nuevos" if opciones.solo_nuevos else "sincronizacion_completa",
               "politica_duplicados": "ultimo_registro_api",
               "incidencias_fuente": incidencias}
    await asyncio.to_thread(guardar_informe, opciones.informe, informe)
    logger.info("Resumen: %s | incidencias_fuente=%s | informe=%s", resultado.model_dump(), len(incidencias), opciones.informe)
    return informe


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", help="Confirma altas y actualización de existentes en una transacción.")
    parser.add_argument("--solo-nuevos", action="store_true", help="Limita opcionalmente la carga a cuentas inexistentes.")
    parser.add_argument("--conexion-desde", type=Path, help="Script legado con URL de Neon; se lee sin ejecutarlo.")
    parser.add_argument("--informe", type=Path, default=OpcionesCarga().informe)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(ejecutar(OpcionesCarga(**vars(args))))
    except BusinessRuleException as exc:
        logger.error("Carga cancelada: %s", exc.message)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
