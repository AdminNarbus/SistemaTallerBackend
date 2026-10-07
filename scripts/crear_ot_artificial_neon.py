"""Carga explícita e idempotente de la OT artificial autorizada para bus 1."""
import ast
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.engine import make_url

import app.models  # noqa: F401
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_solicitud_evidencia import TallerSolicitudEvidencia
from app.modules.taller.services.trazabilidad_estados import RegistroEstadoOT, registrar_evento_estado
from app.modules.taller.services.trazabilidad_fallas import registrar_evento_falla
from app.modules.taller.repository.taller_repository import taller_repository

logger = logging.getLogger(__name__)
DESCRIPTION = "test — PRUEBA ARTIFICIAL / NO REAL. Bus 1 ficticio; fallas e imágenes de prueba."
BLACK_IMAGE = "https://placehold.co/800x600/000000/000000.png?text=TEST"
ACTOR = "test — CARGA ARTIFICIAL"


def neon_url():
    tree = ast.parse(Path("scripts/vincular_ricardo_ot21_neon.py").read_text())
    raw = next(ast.literal_eval(node.value) for node in tree.body
               if isinstance(node, ast.Assign) and any(
                   isinstance(target, ast.Name) and target.id == "NEON_URL"
                   for target in node.targets))
    url = make_url(raw)
    if url.database != "taller" or not url.host.endswith(".neon.tech"):
        raise RuntimeError("La carga requiere la base taller en Neon")
    return url


async def insert_fixture(db):
    existing = await db.scalar(select(TallerSolicitud.id).where(
        TallerSolicitud.descripcion_general == DESCRIPTION))
    if existing:
        photos = (await db.scalars(select(TallerSolicitudEvidencia).where(
            TallerSolicitudEvidencia.solicitud_id == existing))).all()
        for photo in photos:
            photo.detalle_id = None
        return existing
    active = await db.scalar(select(TallerSolicitud.id).where(
        TallerSolicitud.n_bus == "1", TallerSolicitud.estado != "FINALIZADO"))
    if active:
        raise RuntimeError("Bus 1 ya tiene una OT activa; no se modifica")
    now = datetime.now(timezone.utc)
    ot = TallerSolicitud(n_bus="1", estado="PENDIENTE", descripcion_general=DESCRIPTION,
                         foto_url=BLACK_IMAGE, fecha_creacion=now, fecha_actualizacion=now,
                         horas_taller_acumuladas=0)
    db.add(ot)
    await db.flush()
    for number in range(1, 5):
        detail = TallerSolicitudDetalle(
            solicitud_id=ot.id, descripcion_personalizada=f"Falla {number} — PRUEBA ARTIFICIAL / NO REAL",
            falla_nombre_snapshot=f"Falla {number}", categoria_nombre_snapshot="TEST / ARTIFICIAL",
            estado="PENDIENTE", resuelto=False, falta_repuesto=False,
            fecha_creacion=now, fecha_reporte=now)
        db.add(detail)
        await db.flush()
        db.add(TallerSolicitudEvidencia(
            solicitud_id=ot.id, url=BLACK_IMAGE,
            original_filename=f"test_falla_{number}_negro.png", content_type="image/png",
            size_bytes=3702, fecha_creacion=now))
        registrar_evento_falla(db, taller_repository, detalle_id=detail.id,
                              tipo_evento="REPORTADA", actor_id=None, actor_nombre=ACTOR,
                              estado_anterior=None, estado_nuevo="PENDIENTE", fecha_evento=now,
                              comentario=detail.descripcion_personalizada)
    await registrar_evento_estado(db, RegistroEstadoOT(
        solicitud_id=ot.id, estado_anterior=None, estado_nuevo="PENDIENTE",
        actor_id=None, actor_nombre=ACTOR, fecha_evento=now, tipo_evento="CREACION",
        motivo="OT artificial solicitada para pruebas; no corresponde a una reparación real."))
    return ot.id


async def main():
    engine = create_async_engine(neon_url(), connect_args={"timeout": 15})
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            async with db.begin():
                ot_id = await insert_fixture(db)
            details = await db.scalar(select(func.count()).select_from(TallerSolicitudDetalle)
                                      .where(TallerSolicitudDetalle.solicitud_id == ot_id))
            photos = await db.scalar(select(func.count()).select_from(TallerSolicitudEvidencia)
                                     .where(TallerSolicitudEvidencia.solicitud_id == ot_id,
                                            TallerSolicitudEvidencia.detalle_id.is_(None)))
            if details != 4 or photos != 4:
                raise RuntimeError("La verificación requiere cuatro fallas y cuatro fotos de la OT")
            logger.info("Verificado Neon: OT #%s | bus 1 | PENDIENTE | fallas=%s | fotos negras=%s",
                        ot_id, details, photos)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
