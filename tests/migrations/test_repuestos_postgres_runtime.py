"""Concurrencia y esquema real de repuestos en PostgreSQL desechable."""
import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import importlib.util
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test_motivo_salida_estadia import postgres_temporal
from app.core.base import Base
from app.core.exceptions import BusinessRuleException
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.taller.dtos.repuesto_dto import RegistrarRepuestoUtilizadoDTO, AnularRepuestoUtilizadoDTO
from app.modules.taller.models.repuesto import Repuesto
from app.modules.taller.models.taller_repuesto_utilizado import TallerRepuestoUtilizado
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.repository.taller_repository import taller_repository
from app.modules.taller.services.repuesto_service import repuesto_service


async def test_esquema_concurrencia_y_cierre(postgres_temporal, monkeypatch):
    pg = postgres_temporal
    engine = create_async_engine(f"postgresql+asyncpg://migration_test@127.0.0.1:{pg.port}/postgres")
    sesiones = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.modules.taller.services.repuesto_service.publish_event_soon", lambda evento: None)
    tablas = {"repuestos", "taller_repuestos_utilizados"}

    def crear_esquema(conn):
        Base.metadata.create_all(conn, tables=[t for t in Base.metadata.sorted_tables if t.name not in tablas])
        path = Path(__file__).resolve().parents[2] / "alembic/versions/038_repuestos_por_falla.py"
        spec = importlib.util.spec_from_file_location("repuestos_real", path)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        with Operations.context(MigrationContext.configure(conn)):
            modulo.upgrade()
        context = MigrationContext.configure(conn, opts={
            "compare_type": True, "compare_server_default": True,
            "include_object": lambda obj, name, tipo, reflected, compare_to: tipo != "table" or name in tablas,
        })
        assert compare_metadata(context, Base.metadata) == []

    try:
        async with engine.begin() as conn:
            await conn.run_sync(crear_esquema)
        async with sesiones() as db:
            rol = Rol(nombre="SUPERVISOR")
            db.add(rol)
            await db.flush()
            usuario = Usuario(nombre="Supervisor", username="pg-repuestos", password_hash="test", rol_id=rol.id)
            ot = TallerSolicitud(n_bus="PG-REP", es_ot=True, estado="LIBERADO")
            db.add_all([usuario, ot])
            await db.flush()
            falla = TallerSolicitudDetalle(solicitud_id=ot.id, descripcion_personalizada="Fuga", estado_revision="APROBADA")
            articulo = Repuesto(codigo="PG-001", nombre="Válvula", unidad="UN")
            db.add_all([falla, articulo])
            await db.commit()
            sid, did, rid = ot.id, falla.id, articulo.id
            actor = SimpleNamespace(id=usuario.id, rol="SUPERVISOR", nombre_completo="Supervisor")

        async def registrar(operacion):
            async with sesiones() as db:
                dto = RegistrarRepuestoUtilizadoDTO(repuesto_id=rid, cantidad="1.2345", operacion_id=operacion)
                return await repuesto_service.registrar(db, sid, did, dto, actor)

        # Dos transacciones reales compiten por la misma falla y operación.
        operacion = uuid4()
        resultados = await asyncio.wait_for(asyncio.gather(registrar(operacion), registrar(operacion)), timeout=20)
        assert sorted(creado for _, creado in resultados) == [False, True]
        registro_id = resultados[0][0].id
        assert resultados[1][0].id == registro_id
        assert resultados[0][0].cantidad_utilizada == Decimal("1.2345")
        # UUID distintos para el mismo consumo tampoco duplican ni notifican.
        resultados = await asyncio.wait_for(asyncio.gather(registrar(uuid4()), registrar(uuid4())), timeout=20)
        assert all(not creado and salida.id == registro_id for salida, creado in resultados)
        async with sesiones() as db:
            assert await db.scalar(select(func.count()).select_from(TallerRepuestoUtilizado)) == 1
            assert await db.scalar(select(func.count()).select_from(TallerSolicitudComentario)) == 1

        async def anular():
            async with sesiones() as db:
                dto = AnularRepuestoUtilizadoDTO(motivo="Error", operacion_id=uuid4())
                return await repuesto_service.anular(db, sid, did, registro_id, dto, actor)

        anulados = await asyncio.wait_for(asyncio.gather(anular(), anular()), timeout=20)
        assert anulados[0].fecha_anulacion == anulados[1].fecha_anulacion
        async with sesiones() as db:
            assert await db.scalar(select(func.count()).select_from(TallerSolicitudComentario)) == 2
        # El alta histórica no reactiva el consumo anulado.
        replay, creado = await registrar(operacion)
        assert not creado and replay.id == registro_id
        async with sesiones() as db:
            assert await db.scalar(select(func.count()).select_from(TallerRepuestoUtilizado).where(TallerRepuestoUtilizado.fecha_anulacion.is_(None))) == 0

        # El registro espera al cierre y valida el estado confirmado por otra sesión.
        async with sesiones() as cierre:
            await taller_repository.lock_solicitud_estado(cierre, sid)
            ot = await cierre.get(TallerSolicitud, sid)
            ot.estado = "FINALIZADO"
            await cierre.flush()
            tarea = asyncio.create_task(registrar(uuid4()))
            await asyncio.sleep(0.05)
            await cierre.commit()
            with pytest.raises(BusinessRuleException, match="abierta"):
                await asyncio.wait_for(tarea, timeout=20)
    finally:
        await engine.dispose()
