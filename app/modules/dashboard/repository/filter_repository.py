from sqlalchemy import Integer, String, cast, func, select, union_all

from app.modules.dashboard.repository.base import ReadRepository
from app.modules.dashboard.repository.relations import B, D
from app.modules.dashboard.repository.sql_expressions import BusKey, MonthKey


class FilterRepository(ReadRepository):
    async def options(self, request):
        resource, filters = request
        statement = getattr(self, f"_{resource}")(filters)
        return await self.page(statement, filters)

    def _buses(self, filters):
        if filters.contexto == "maquina":
            stmt = select(B.c.id.label("bus_id"), B.c.n_bus, B.c.patente).where(
                B.c.is_active.is_(True)
            )
            if filters.q:
                stmt = stmt.where(
                    BusKey(B.c.n_bus).startswith(self._prefix(filters.q), autoescape=True)
                )
            return stmt.order_by(B.c.n_bus, B.c.id)
        loose = filters.model_copy(update={"bus_id": None, "n_bus": None})
        rows = self.queries.filtered(loose).cte("dash_bus_options")
        stmt = (
            select(rows.c.bus_id, rows.c.n_bus, B.c.patente)
            .outerjoin(B, B.c.id == rows.c.bus_id)
            .distinct()
        )
        if filters.q:
            stmt = stmt.where(
                BusKey(rows.c.n_bus).startswith(self._prefix(filters.q), autoescape=True)
            )
        return stmt.order_by(rows.c.n_bus, rows.c.bus_id)

    def _solicitudes(self, filters):
        loose = filters.model_copy(update={"solicitud_id": None})
        rows = self.queries.filtered(loose).cte("dash_order_options")
        stmt = select(rows.c.id, rows.c.n_bus, rows.c.es_ot)
        if filters.q:
            stmt = stmt.where(
                cast(rows.c.id, String).startswith(self._prefix(filters.q), autoescape=True)
            )
        return stmt.order_by(rows.c.id)

    def _mecanicos(self, filters):
        m = self.relations.mechanics
        stmt = select(m)
        if filters.q:
            stmt = stmt.where(
                func.lower(m.c.nombre_completo).contains(filters.q.lower(), autoescape=True)
            )
        return stmt.order_by(m.c.nombre_completo, m.c.id)

    def _periodos(self, filters):
        if filters.contexto == "cronologia":
            rows = self._timeline_period_source(filters)
            period = MonthKey(rows.c.fecha_evento)
        else:
            loose = filters.model_copy(update={"meses": [], "anios": []})
            rows = self.queries.filtered(loose).cte("dash_period_orders")
            dates = union_all(
                select(rows.c.periodo.label("periodo")),
                select(MonthKey(rows.c.fecha_termino)).where(rows.c.fecha_termino.is_not(None)),
                select(MonthKey(func.coalesce(D.c.fecha_reporte, D.c.fecha_creacion))).select_from(D.join(rows, rows.c.id == D.c.solicitud_id)),
                select(MonthKey(self.relations.attended_faults.c.fecha_atencion)).select_from(
                    self.relations.attended_faults.join(D, D.c.id == self.relations.attended_faults.c.detalle_id).join(rows, rows.c.id == D.c.solicitud_id)
                ),
                select(MonthKey(self.relations.attentions.c.fecha_atencion)).select_from(
                    self.relations.attentions.join(rows, rows.c.id == self.relations.attentions.c.solicitud_id)
                ),
            ).cte("dash_period_dates")
            period = dates.c.periodo
        return (
            select(
                period.label("periodo"),
                cast(func.substr(period, 6, 2), Integer).label("mes"),
                cast(func.substr(period, 1, 4), Integer).label("anio"),
            )
            .where(period.is_not(None))
            .distinct()
            .order_by(period.desc())
        )

    def _timeline_period_source(self, filters):
        from app.modules.dashboard.dtos.filtros_dto import TimelineQueryDTO
        from app.modules.dashboard.repository.cronologia_repository import CronologiaRepository

        common = {
            key: value
            for key, value in filters.model_dump().items()
            if key in TimelineQueryDTO.model_fields
        }
        query = TimelineQueryDTO(**common)
        return CronologiaRepository(self.db).milestones((filters.bus_id, query))

    @staticmethod
    def _prefix(value):
        return value.strip().removeprefix("#").strip().lstrip("0") or "0"
