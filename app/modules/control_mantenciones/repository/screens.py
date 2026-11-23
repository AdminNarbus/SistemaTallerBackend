"""Consultas de pantalla y series acotadas por bus y período."""

from typing import Any

from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from sqlalchemy import JSON, column, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.modules.buses.models.bus import Bus
from app.modules.control_mantenciones.dtos.contracts import Filtros
from app.modules.control_mantenciones.models.entities import ControlEvento as Evento
from app.modules.control_mantenciones.models.entities import ControlKilometraje as Km
from app.modules.control_mantenciones.repository.queries import (
    historial_consulta,
    panel_consulta,
)
from app.modules.control_mantenciones.repository.records import RecordsRepository
from app.modules.control_mantenciones.services.domain import (
    PASO_EJE_Y,
    desplazar_mes,
    hoy,
    proyectar,
)
from app.modules.control_mantenciones.dtos.serialization import snapshot


class ReadRepository:
    def __init__(self, db: AsyncSession) -> Any:
        self.db, self.repo = db, RecordsRepository()

    async def panel(self, filtros: Filtros) -> dict:
        consulta = panel_consulta(
            filtros, hoy(), settings.CONTROL_MANTENCIONES_DIAS_RECIENTES
        )
        items, total = await self.repo.listar(self.db, consulta, filtros)
        base = consulta.order_by(None).subquery()
        contadores = (
            await self.db.execute(
                select(base.c.estado_kilometraje, func.count()).group_by(
                    base.c.estado_kilometraje
                )
            )
        ).all()
        return {
            "items": items,
            "total": total,
            "skip": filtros.skip,
            "limit": filtros.limit,
            "contadores": dict(contadores),
        }

    async def ficha(self, bus_id: int) -> dict:
        consulta = panel_consulta(
            Filtros(bus_id=bus_id), hoy(), settings.CONTROL_MANTENCIONES_DIAS_RECIENTES
        )
        fila = (await self.db.execute(consulta)).mappings().first()
        if fila is None:
            return None
        return dict(fila)

    async def referencias_odometro(self, bus_id: int, fecha: date) -> tuple[dict | None, dict | None]:
        lecturas = select(Km.fecha, Km.kilometraje).where(
            Km.bus_id == bus_id, Km.estado == "aceptado"
        )
        anterior = lecturas.where(Km.fecha < fecha).order_by(Km.fecha.desc(), Km.id.desc())
        posterior = lecturas.where(Km.fecha > fecha).order_by(Km.fecha, Km.id.desc())
        previa = (await self.db.execute(anterior.limit(1))).mappings().first()
        siguiente = (await self.db.execute(posterior.limit(1))).mappings().first()
        return (dict(previa) if previa else None, dict(siguiente) if siguiente else None)

    async def historial(self, filtros: Filtros) -> dict:
        items, total = await self.repo.listar(
            self.db, historial_consulta(filtros), filtros
        )
        if filtros.bus_id is not None:
            await self.agregar_lecturas_anteriores(items)
        return {
            "items": items,
            "total": total,
            "skip": filtros.skip,
            "limit": filtros.limit,
        }

    async def agregar_lecturas_anteriores(self, filas: list[dict]) -> None:
        pendientes = [
            fila for fila in filas
            if fila["tipo"] == "kilometraje" and fila["estado"] == "pendiente"
        ]
        if not pendientes:
            return
        contexto = await self.repo.contexto(self.db, pendientes)
        for indice, fila in enumerate(pendientes):
            lectura = contexto.get(indice, {})
            if lectura.get("anterior_fecha") is not None:
                fila["anterior"] = {
                    "fecha": lectura["anterior_fecha"],
                    "kilometraje": lectura["anterior_km"],
                }

    def consulta_eventos(self, filtros: Filtros, tipo: str | None = None) -> Any:
        columnas = [c for c in Evento.__table__.columns if c.name != "metadatos"]
        consulta = (
            select(
                *columnas,
                Evento.metadatos.op("-")("revision").label("metadatos"),
                Bus.n_bus.label("numero_bus"),
            )
            .select_from(Evento)
            .outerjoin(Bus, Bus.id == Evento.bus_id)
        )
        if tipo:
            consulta = consulta.where(Evento.tipo == tipo)
        if filtros.bus_id:
            consulta = consulta.where(Evento.bus_id == filtros.bus_id)
        if filtros.mantencion_id:
            consulta = consulta.where(Evento.mantencion_id == filtros.mantencion_id)
        if filtros.buscar:
            consulta = consulta.where(
                or_(
                    Evento.tipo.ilike(f"%{filtros.buscar}%"),
                    Evento.comentario.ilike(f"%{filtros.buscar}%"),
                    Evento.metadatos["nombre_archivo"].astext.ilike(
                        f"%{filtros.buscar}%"
                    ),
                )
            )
        if filtros.desde:
            consulta = consulta.where(func.date(Evento.created_at) >= filtros.desde)
        if filtros.hasta:
            consulta = consulta.where(func.date(Evento.created_at) <= filtros.hasta)
        return consulta.order_by(Evento.created_at.desc(), Evento.id.desc())

    async def eventos(self, filtros: Filtros, tipo: str | None = None) -> dict:
        items, total = await self.repo.listar(
            self.db, self.consulta_eventos(filtros, tipo), filtros
        )
        return {
            "items": items,
            "total": total,
            "skip": filtros.skip,
            "limit": filtros.limit,
        }

    async def detalle(self, modelo: Any, identificador: int) -> dict:
        registro = await self.db.get(modelo, identificador)
        if registro is None:
            return None
        return snapshot(registro)

    async def serie_periodo(self, filtros: Filtros) -> list[dict]:
        base = historial_consulta(filtros).subquery()
        consulta = (
            select(base)
            .where(
                base.c.fecha.is_not(None),
                base.c.kilometraje.is_not(None),
                base.c.kilometraje >= 0,
                or_(base.c.tipo == "kilometraje", base.c.activa.is_(True)),
            )
            .order_by(base.c.fecha, base.c.id)
        )
        filas = [dict(r) for r in (await self.db.execute(consulta)).mappings().all()]
        return [
            {**r, "estado": "aceptado" if r["tipo"] == "mantencion" else r["estado"]}
            for r in filas
        ]

    async def punto_anterior(self, bus_id: int, inicio: Any) -> dict | None:
        base = historial_consulta(
            Filtros(bus_id=bus_id, hasta=inicio - timedelta(days=1))
        ).subquery()
        consulta = (
            select(base)
            .where(
                base.c.kilometraje.is_not(None),
                or_(
                    base.c.estado == "aceptado",
                    (base.c.tipo == "mantencion") & base.c.activa.is_(True),
                ),
            )
            .order_by(base.c.fecha.desc(), base.c.id.desc())
            .limit(1)
        )
        fila = (await self.db.execute(consulta)).mappings().first()
        return dict(fila) if fila else None

    async def detalle_carga(self, identificador: int) -> dict:
        consulta = self.consulta_eventos(Filtros(), "carga_confirmada").where(
            Evento.id == identificador
        )
        registro = (await self.db.execute(consulta)).mappings().first()
        if registro is None:
            return None
        return dict(registro)

    async def filas_carga(self, identificador: int, filtros: Filtros) -> dict:
        await self.detalle_carga(identificador)
        resultados = Evento.metadatos["revision"]["resultados"]
        tabla = (
            func.jsonb_array_elements(resultados)
            .table_valued(column("value", Evento.metadatos.type))
            .lateral()
        )
        consulta = (
            select(tabla.c.value)
            .select_from(Evento)
            .join(tabla, literal(True))
            .where(Evento.id == identificador)
        )
        if filtros.estado:
            consulta = consulta.where(tabla.c.value["estado"].astext == filtros.estado)
        total = await self.db.scalar(
            select(func.count()).select_from(consulta.subquery())
        )
        items = list(
            (
                await self.db.scalars(
                    consulta.offset(filtros.skip).limit(filtros.limit)
                )
            ).all()
        )
        return {
            "items": items,
            "total": total or 0,
            "skip": filtros.skip,
            "limit": filtros.limit,
        }
