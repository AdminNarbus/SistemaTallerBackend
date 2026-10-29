"""Verifica consultas y concurrencia contra PostgreSQL desechable local."""
import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.base import Base
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.buses.models.bus import Bus
from app.modules.taller.dtos.bus_mecanico_dto import AgregarFallaBusDTO, BusesMecanicoFiltroDTO
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.services.buses_taller_service import BusesTallerService, RegistroFallaBus
from app.modules.taller.services.solicitud_service import SolicitudService
from app.modules.supervision.services.supervision_service import SupervisionService
from app.modules.taller.services.aprobacion_ot_service import AprobacionOT, aprobar_solicitud
from test_motivo_salida_estadia import postgres_temporal


@pytest.fixture
async def sesiones_postgres(postgres_temporal):
    puerto = postgres_temporal.port
    engine = create_async_engine(f"postgresql+asyncpg://migration_test@127.0.0.1:{puerto}/postgres")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def test_reportes_concurrentes_crean_una_sola_ot_y_preservan_autoasignacion(sesiones_postgres):
    async with sesiones_postgres() as db:
        db.add(Rol(id=2, nombre="MECANICO"))
        await db.flush()
        db.add_all([
            Usuario(id=2, username="mec2", nombre="Pedro", apellido="Mecánico", rol_id=2, password_hash="test", is_active=True),
            Usuario(id=3, username="mec3", nombre="Ana", apellido="Mecánica", rol_id=2, password_hash="test", is_active=True),
            Bus(id=1, n_bus="PG100", patente="PG-100", is_active=True, en_taller=False),
            Bus(id=2, n_bus="PG200", patente="PG-200", is_active=True, en_taller=False),
        ])
        await db.commit()

    async def reportar(actor_id, autoasignar):
        actor = UsuarioResponseDTO(id=actor_id, username=f"mec{actor_id}", nombre_completo=f"Mecánico {actor_id}", rol="MECANICO", is_active=True)
        async with sesiones_postgres() as db:
            return await BusesTallerService().agregar_falla(db, RegistroFallaBus(
                bus_id=1, actor=actor, falla=AgregarFallaBusDTO(nombre=f"Falla {actor_id}", autoasignar=autoasignar),
            ))

    primero, segundo = await asyncio.wait_for(asyncio.gather(reportar(2, False), reportar(3, True)), timeout=20)

    assert primero.id == segundo.id
    async with sesiones_postgres() as db:
        assert await db.scalar(select(func.count()).select_from(TallerSolicitud)) == 1
        assert await db.scalar(select(func.count()).select_from(TallerSolicitudDetalle)) == 2
        asignaciones = (await db.execute(select(TallerAsignacionFalla))).scalars().all()
        assert len(asignaciones) == 1
        assert asignaciones[0].mecanico_id == 3
        assert asignaciones[0].is_activo
        buses, total = await BusesTallerService().listar(db, BusesMecanicoFiltroDTO())
        assert total == 2

        assert [bus.bus_id for bus in buses] == [1, 2]
        assert buses[0].ot.id == primero.id
        assert buses[0].ot.numero_fallas_pendientes == 2
        assert buses[0].ot.creador_nombre in ("Pedro Mecánico", "Ana Mecánica")
        assert buses[0].ot.fecha_creacion == primero.fecha_creacion
        assert await db.scalar(select(Bus.en_taller).where(Bus.id == 1)) is True
        assert buses[1].ot is None
        vacia, total = await BusesTallerService().listar(db, BusesMecanicoFiltroDTO(skip=100))
        assert vacia == []
        assert total == 2


async def test_aprobacion_concurrente_y_lecturas_nativas_ocultan_estado(sesiones_postgres):
    async with sesiones_postgres() as db:
        db.add(Rol(id=2, nombre="MECANICO"))
        await db.flush()
        db.add_all([
            Usuario(id=2, username="reportante", nombre="Pedro", rol_id=2, password_hash="test", is_active=True),
            Bus(id=1, n_bus="PG-SOL", patente="PG-SOL", is_active=True, en_taller=False),
        ])
        await db.commit()
        actor = UsuarioResponseDTO(id=2, username="reportante", nombre_completo="Pedro", rol="MECANICO", is_active=True)
        solicitud = await BusesTallerService().agregar_falla(db, RegistroFallaBus(
            bus_id=1, actor=actor, falla=AgregarFallaBusDTO(nombre="Reporte sin asignar"),
        ))
        sid = solicitud.id
        detalle = await SolicitudService().get_solicitud(db, sid)
        assert detalle.es_ot is False and detalle.estado is None
        pendientes = await SolicitudService().list_pendientes(db)
        assert pendientes[0].es_ot is False and pendientes[0].estado is None
        auditoria = await SupervisionService().get_auditoria_solicitudes(db)
        assert auditoria[0].es_ot is False and auditoria[0].estado is None

    async def aprobar():
        async with sesiones_postgres() as db:
            return await aprobar_solicitud(db, sid, AprobacionOT(2, "Pedro", "Aprobación concurrente de prueba"))

    aprobadas = await asyncio.wait_for(asyncio.gather(aprobar(), aprobar()), timeout=20)
    assert all(ot.es_ot and ot.estado == "PENDIENTE" for ot in aprobadas)
    from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
    async with sesiones_postgres() as db:
        assert await db.scalar(select(func.count()).select_from(TallerSolicitudComentario).where(
            TallerSolicitudComentario.comentario.like("Solicitud aprobada como OT.%"),
        )) == 1
