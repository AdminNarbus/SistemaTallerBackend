from sqlalchemy import func, select

from app.modules.dashboard.repository.base import ReadRepository, count_when
from app.modules.dashboard.repository.relations import B, D, V, fault_description
from app.modules.dashboard.repository.sql_expressions import MonthKey


class BusDashboardRepository(ReadRepository):
    async def bus(self, bus_id):
        rows = await self.rows(select(B.c.id, B.c.n_bus, B.c.patente).where(B.c.id == bus_id))
        return rows[0] if rows else None

    def bus_orders(self, request):
        bus_id, _ = request
        return select(self.relations.orders).where(self.relations.orders.c.bus_id == bus_id)

    async def latest(self, request):
        rows = self.bus_orders(request).cte("dash_bus_latest")
        result = await self.rows(
            select(rows.c.id, rows.c.estado)
            .order_by(rows.c.fecha_creacion.desc(), rows.c.id.desc())
            .limit(1)
        )
        return result[0] if result else None

    async def counts(self, request):
        rows = self.bus_orders(request).cte("dash_bus_count_orders")
        episodes = self.relations.attentions
        visits = (
            select(func.count())
            .select_from(rows.join(episodes, episodes.c.solicitud_id == rows.c.id))
            .where(rows.c.es_ot.is_(True))
            .scalar_subquery()
        )
        return await self.one(
            select(
                visits.label("visitas"),
                count_when(D.c.estado == "PENDIENTE").label("pendientes"),
                count_when(D.c.estado == "INCOMPLETA").label("incompletas"),
                count_when(D.c.estado == "RESUELTA").label("resueltas"),
            ).select_from(D.join(rows, rows.c.id == D.c.solicitud_id))
        )

    async def recurrences(self, request):
        rows = self.bus_orders(request).cte("dash_bus_recurrence_orders")
        r = self.relations.recurrences
        latest = MonthKey(func.now())
        count = (
            select(func.count())
            .select_from(r.join(rows, rows.c.id == r.c.solicitud_id))
            .where(r.c.periodo == latest)
            .scalar_subquery()
        )
        return await self.one(select(latest.label("periodo"), count.label("cantidad")))

    async def fault_groups(self, request):
        _, filters = request
        rows = self.bus_orders(request).cte("dash_bus_fault_orders")
        description = fault_description()
        statement = (
            select(description.label("descripcion"), func.count().label("cantidad"))
            .select_from(D.join(rows, rows.c.id == D.c.solicitud_id))
            .where(D.c.estado == filters.estado_falla)
            .group_by(description)
            .order_by(description)
        )
        return await self.page(statement, filters)

    async def fault_orders(self, request):
        _, filters = request
        rows = self.bus_orders(request).cte("dash_bus_fault_related")
        statement = (
            select(D.c.solicitud_id)
            .join(rows, rows.c.id == D.c.solicitud_id)
            .where(D.c.estado == filters.estado_falla, fault_description() == filters.descripcion)
            .distinct()
            .order_by(D.c.solicitud_id.desc())
        )
        return await self.page(statement, filters)
