"""Consultas tipadas y persistencia sin cerrar transacciones."""

from typing import Any

from datetime import date
from typing import Any

from sqlalchemy import (
    Date,
    Integer,
    String,
    any_,
    and_,
    case,
    cast,
    delete,
    func,
    literal,
    or_,
    select,
    union_all,
    values,
    column,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import ARRAY

from app.modules.buses.models.bus import Bus
from app.modules.control_mantenciones.models.entities import (
    ControlEvento as Evento,
    ControlKilometraje as Kilometraje,
    ControlMantencion as Mantencion,
)


def registros_validos(excluir: int | None = None) -> Any:
    lecturas = select(
        Kilometraje.bus_id.label("bus_id"),
        Kilometraje.fecha.label("fecha"),
        Kilometraje.kilometraje.label("kilometraje"),
    ).where(Kilometraje.estado == "aceptado")
    if excluir is not None:
        lecturas = lecturas.where(Kilometraje.id != excluir)
    mantenciones = select(
        Mantencion.bus_id, Mantencion.fecha, Mantencion.kilometraje
    ).where(
        Mantencion.activa.is_(True),
        Mantencion.fecha.is_not(None),
        Mantencion.kilometraje.is_not(None),
    )
    return union_all(lecturas, mantenciones).cte("registros_validos")


class RecordsRepository:
    async def obtener(self, db: AsyncSession, modelo: Any, identificador: int) -> Any:
        if modelo in (Mantencion, Kilometraje):
            bus_id = await db.scalar(
                select(modelo.bus_id).where(modelo.id == identificador)
            )
            if bus_id is not None:
                await self.bloquear_buses(db, [bus_id])
        consulta = (
            select(modelo)
            .where(modelo.id == identificador)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await db.scalar(consulta)

    async def agregar(self, db: AsyncSession, registro: Any) -> Any:
        db.add(registro)
        await db.flush()
        return registro

    async def agregar_lote(self, db: AsyncSession, registros: list) -> None:
        db.add_all(registros)
        await db.flush()

    async def eliminar(self, db: AsyncSession, registro: Any) -> None:
        await db.delete(registro)
        await db.flush()

    async def buses(self, db: AsyncSession, numeros: list[str]) -> list[Bus]:
        consulta = (
            select(Bus)
            .where(
                Bus.n_bus == any_(literal(numeros, type_=ARRAY(String))),
                Bus.is_active.is_(True),
            )
            .order_by(Bus.id)
        )
        return list((await db.scalars(consulta)).all())

    async def bloquear_buses(self, db: AsyncSession, ids: list[int]) -> None:
        await db.execute(
            select(Bus.id)
            .where(Bus.id == any_(literal(ids, type_=ARRAY(Integer))))
            .order_by(Bus.id)
            .with_for_update()
        )

    async def carga_por_clave(self, db: AsyncSession, clave: Any) -> Any:
        return await db.scalar(select(Evento).where(Evento.clave_operacion == clave))

    async def bloquear_clave(self, db: AsyncSession, clave: Any) -> None:
        # Lock transaccional estable, compartido por reintentos concurrentes del mismo UUID.
        llave = int.from_bytes(clave.bytes[:8], "big", signed=True)
        await db.execute(select(func.pg_advisory_xact_lock(llave)))

    async def contexto(
        self, db: AsyncSession, candidatos: list[dict], excluir: int | None = None
    ) -> dict:
        if not candidatos:
            return {}
        consulta = consulta_contextos(candidatos, excluir)
        return {
            row.indice: dict(row._mapping) for row in (await db.execute(consulta)).all()
        }

    async def duplicados(
        self, db: AsyncSession, candidatos: list[dict], excluir: int | None = None
    ) -> set:
        if not candidatos:
            return set()
        ids = {c["bus_id"] for c in candidatos if c["bus_id"]}
        fechas = {c["fecha"] for c in candidatos if c["fecha"]}
        consulta = select(
            Kilometraje.bus_id, Kilometraje.fecha, Kilometraje.kilometraje
        ).where(
            Kilometraje.bus_id.in_(ids),
            Kilometraje.fecha.in_(fechas),
            Kilometraje.estado == "aceptado",
        )
        if excluir is not None:
            consulta = consulta.where(Kilometraje.id != excluir)
        return set((await db.execute(consulta)).all())

    async def registros_carga(
        self, db: AsyncSession, carga_id: int
    ) -> list[Kilometraje]:
        return list(
            (
                await db.execute(
                    select(Kilometraje.id, Kilometraje.bus_id)
                    .where(Kilometraje.evento_carga_id == carga_id)
                    .order_by(Kilometraje.id)
                )
            ).all()
        )

    async def version_intervalo(self, db: AsyncSession, bus_id: int) -> int:
        consulta = select(func.coalesce(func.max(Evento.id), 0)).where(
            Evento.bus_id == bus_id, Evento.tipo == "intervalo_cambiado"
        )
        return await db.scalar(consulta)

    async def eliminar_lecturas_carga(self, db: AsyncSession, carga_id: int) -> None:
        await db.execute(
            delete(Kilometraje).where(Kilometraje.evento_carga_id == carga_id)
        )

    async def borrar_eventos_lecturas(self, db: AsyncSession, ids: list[int]) -> None:
        await db.execute(delete(Evento).where(Evento.kilometraje_id.in_(ids)))

    async def listar(
        self, db: AsyncSession, consulta: Any, filtros: Any
    ) -> tuple[list, int]:
        total = await db.scalar(
            select(func.count()).select_from(consulta.order_by(None).subquery())
        )
        filas = (
            (await db.execute(consulta.offset(filtros.skip).limit(filtros.limit)))
            .mappings()
            .all()
        )
        return [dict(fila) for fila in filas], total or 0


def tabla_candidatos(candidatos: list[dict]) -> Any:
    columnas = [
        column("indice", Integer),
        column("bus_id", Integer),
        column("fecha", Date),
    ]
    datos = [
        (
            i,
            cast(literal(c["bus_id"], Integer), Integer),
            cast(literal(c["fecha"], Date), Date),
        )
        for i, c in enumerate(candidatos)
    ]
    return values(*columnas).data(datos).alias("candidatos")


def contexto_anterior(base: Any, tabla: Any) -> Any:
    condicion = or_(tabla.c.fecha.is_(None), base.c.fecha < tabla.c.fecha)
    consulta = select(base.c.fecha, base.c.kilometraje).where(
        base.c.bus_id == tabla.c.bus_id, condicion
    )
    return (
        consulta.order_by(base.c.fecha.desc(), base.c.kilometraje.desc())
        .limit(1)
        .lateral("anterior")
    )


def contexto_posterior(base: Any, tabla: Any) -> Any:
    consulta = select(base.c.fecha, base.c.kilometraje).where(
        base.c.bus_id == tabla.c.bus_id, base.c.fecha > tabla.c.fecha
    )
    return (
        consulta.order_by(base.c.fecha, base.c.kilometraje)
        .limit(1)
        .lateral("posterior")
    )


def consulta_contextos(candidatos: list[dict], excluir: int | None = None) -> Any:
    base, tabla = registros_validos(excluir), tabla_candidatos(candidatos)
    anterior, posterior = contexto_anterior(base, tabla), contexto_posterior(
        base, tabla
    )
    mismas = (
        select(func.array_agg(func.distinct(base.c.kilometraje)))
        .where(base.c.bus_id == tabla.c.bus_id, base.c.fecha == tabla.c.fecha)
        .scalar_subquery()
    )
    columnas = [
        tabla.c.indice,
        anterior.c.fecha.label("anterior_fecha"),
        anterior.c.kilometraje.label("anterior_km"),
        posterior.c.fecha.label("posterior_fecha"),
        posterior.c.kilometraje.label("posterior_km"),
        mismas.label("mismos"),
    ]
    origen = tabla.outerjoin(anterior, literal(True)).outerjoin(
        posterior, literal(True)
    )
    return select(*columnas).select_from(origen)
