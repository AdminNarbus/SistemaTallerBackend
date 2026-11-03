from sqlalchemy import and_, case, func, literal, select, union_all

from app.modules.dashboard.constants import AGE_GROUPS, RANKING_LIMIT, WORKSHOP_GROUPS
from app.modules.dashboard.repository.base import (
    ReadRepository,
    count_when,
    percentage,
    valid_duration,
)
from app.modules.dashboard.repository.relations import B, D, E, V
from app.modules.dashboard.repository.sql_expressions import (
    EndOfDay,
    Median,
    MonthKey,
    WeekKey,
)


class DashboardRepository(ReadRepository):
    async def historical_states(self, filters):
        rows = self.queries.filtered(filters).cte("dash_filtered_states")
        return await self.one(
            select(
                func.count().label("total_ot"),
                count_when(rows.c.estado == "FINALIZADO").label("finalizadas_ot"),
                count_when(rows.c.es_ot.is_(False)).label("reportadas_ot"),
            ).select_from(rows)
        )

    async def current_states(self, filters):
        rows = self.queries.latest(filters).cte("dash_state_current")
        fields = [
            count_when(rows.c.es_ot.is_(True) & (rows.c.estado == state)).label(label)
            for state, label in (
                ("PENDIENTE", "pendientes_buses"),
                ("EN_REPARACION", "en_reparacion_buses"),
                ("LIBERADO", "liberados_buses"),
            )
        ]
        fields.insert(0, count_when(rows.c.es_ot.is_(False)).label("solicitadas_buses"))
        return await self.one(select(*fields).select_from(rows))

    async def durations(self, filters):
        rows = self.queries.filtered(filters).cte("dash_duration_orders")
        fields = []
        for name in ("respuesta", "reparacion", "completo"):
            value = rows.c[f"{name}_raw"]
            valid = valid_duration(value)
            fields.extend(
                (
                    func.avg(valid).label(f"{name}_promedio"),
                    Median(valid).label(f"{name}_mediana"),
                    func.count(valid).label(f"{name}_validos"),
                    count_when(value.is_(None)).label(f"{name}_sin_datos"),
                    count_when(value < 0).label(f"{name}_invalidos"),
                )
            )
        return await self.one(select(*fields).select_from(rows))

    async def monthly(self, filters):
        period = MonthKey(func.now())
        loose = filters.model_copy(update={"meses": [], "anios": []})
        filtered = self.queries.filtered(loose).cte("dash_monthly_filtered")
        orders = select(filtered).where(filtered.c.periodo == period).cte("dash_monthly_orders")
        ot = (
            select(
                func.count().label("total"),
                count_when(orders.c.fecha_termino.is_not(None)).label("atendidas"),
            )
            .select_from(orders)
            .cte("dash_monthly_ot_counts")
        )
        faults = (
            select(
                func.count().label("total"),
                count_when(self.relations.attended_faults.c.detalle_id.is_not(None) | D.c.estado.in_(["RESUELTA", "INCOMPLETA"])).label("atendidas"),
            )
            .select_from(
                D.join(filtered, filtered.c.id == D.c.solicitud_id).outerjoin(
                    self.relations.attended_faults,
                    self.relations.attended_faults.c.detalle_id == D.c.id,
                )
            )
            .where(MonthKey(func.coalesce(D.c.fecha_reporte, D.c.fecha_creacion)) == period)
            .cte("dash_monthly_fault_counts")
        )
        r = self.relations.recurrences
        recurrence = (
            select(func.count())
            .select_from(r.join(filtered, filtered.c.id == r.c.solicitud_id))
            .where(r.c.periodo == period)
            .scalar_subquery()
        )
        return await self.one(
            select(
                period.label("periodo"),
                ot.c.total.label("ot_totales"),
                ot.c.atendidas.label("ot_atendidas"),
                percentage(ot.c.atendidas, ot.c.total).label("porcentaje_ot_atendidas"),
                faults.c.total.label("fallas_reportadas"),
                faults.c.atendidas.label("fallas_atendidas"),
                percentage(faults.c.atendidas, faults.c.total).label("porcentaje_fallas_atendidas"),
                recurrence.label("reincidencias"),
            ).select_from(ot.join(faults, literal(True)))
        )

    async def orders(self, filters):
        rows = self.queries.selected(filters).cte("dash_list_orders")
        faults = select(func.count()).where(D.c.solicitud_id == rows.c.id).scalar_subquery()
        stmt = select(
            rows.c.id,
            rows.c.bus_id,
            rows.c.n_bus,
            rows.c.estado,
            rows.c.es_ot,
            faults.label("total_fallas"),
            rows.c.fecha_creacion,
            rows.c.fecha_creacion_ot,
            rows.c.fecha_termino,
            valid_duration(rows.c.total_raw).label("completo_horas"),
        ).order_by(rows.c.fecha_creacion.desc(), rows.c.id.desc())
        return await self.page(stmt, filters)

    async def series(self, name, filters):
        statement = getattr(self, f"_{name.replace('-', '_')}")(filters)
        return await self.page(statement, filters)

    def _tendencia(self, filters):
        loose = filters.model_copy(update={"meses": [], "anios": []})
        rows = self.queries.filtered(loose).cte("dash_trend_orders")
        periods = filters.periodos
        points = union_all(
            select(
                WeekKey(rows.c.fecha_creacion).label("semana"),
                literal(1).label("creadas"),
                literal(0).label("terminadas"),
            ).where(MonthKey(rows.c.fecha_creacion).in_(periods) if periods else literal(True)),
            select(WeekKey(rows.c.fecha_termino), literal(0), literal(1)).where(
                rows.c.fecha_termino.is_not(None),
                MonthKey(rows.c.fecha_termino).in_(periods) if periods else literal(True),
            ),
        ).cte("dash_trend_points")
        return (
            select(
                points.c.semana,
                func.sum(points.c.creadas).label("creadas"),
                func.sum(points.c.terminadas).label("terminadas"),
            )
            .group_by(points.c.semana)
            .order_by(points.c.semana)
        )

    def _antiguedad(self, filters):
        rows = self.queries.open_latest(filters).cte("dash_aging_orders")
        classified = select(self.queries.age_group(rows).label("grupo")).cte("dash_aging_groups")
        parts = [
            select(
                literal(group).label("grupo"),
                select(func.count())
                .select_from(classified)
                .where(classified.c.grupo == group)
                .scalar_subquery()
                .label("cantidad"),
                literal(index).label("orden"),
            )
            for index, group in enumerate(AGE_GROUPS)
        ]
        all_groups = union_all(*parts).subquery()
        return select(all_groups.c.grupo, all_groups.c.cantidad).order_by(all_groups.c.orden)

    async def age_cutoff(self):
        return (await self.one(select(func.now().label("cutoff"))))["cutoff"]

    def _mecanicos(self, filters):
        rows = self.queries.filtered(filters.model_copy(update={"meses": [], "anios": []})).cte("dash_mechanic_orders")
        p, m = self.relations.fault_participants, self.relations.mechanics
        attended = self.relations.attended_faults
        counts = (
            select(p.c.mecanico_id, func.count(func.distinct(p.c.detalle_id)).label("cantidad"))
            .join(rows, rows.c.id == p.c.solicitud_id)
            .join(attended, attended.c.detalle_id == p.c.detalle_id)
            .where(MonthKey(attended.c.fecha_atencion).in_(filters.periodos) if filters.periodos else literal(True))
            .group_by(p.c.mecanico_id)
            .subquery()
        )
        return (
            select(
                m.c.id.label("mecanico_id"),
                m.c.nombre_completo,
                func.coalesce(counts.c.cantidad, 0).label("fallas_unicas"),
            )
            .outerjoin(counts, counts.c.mecanico_id == m.c.id)
            .order_by(func.coalesce(counts.c.cantidad, 0).desc(), m.c.id)
        )

    def _ranking(self, filters, table):
        rows = self.queries.chart(filters).cte("dash_ranking_orders")
        ranked = (
            select(rows.c.bus_id, B.c.n_bus, func.count(table.c.id).label("cantidad"))
            .select_from(
                rows.join(table, table.c.solicitud_id == rows.c.id).join(B, B.c.id == rows.c.bus_id)
            )
            .group_by(rows.c.bus_id, B.c.n_bus)
            .order_by(func.count(table.c.id).desc(), rows.c.bus_id)
            .limit(RANKING_LIMIT)
            .subquery()
        )
        return select(ranked).order_by(ranked.c.cantidad.desc(), ranked.c.bus_id)

    def _buses_fallas(self, filters):
        rows = self.queries.filtered(filters.model_copy(update={"meses": [], "anios": []})).cte("dash_fault_ranking_orders")
        count = func.count(D.c.id)
        stmt = (
            select(rows.c.bus_id, B.c.n_bus, count.label("cantidad"))
            .select_from(rows.join(D, D.c.solicitud_id == rows.c.id).join(B, B.c.id == rows.c.bus_id))
            .where(MonthKey(func.coalesce(D.c.fecha_reporte, D.c.fecha_creacion)).in_(filters.periodos) if filters.periodos else literal(True))
            .group_by(rows.c.bus_id, B.c.n_bus)
            .order_by(count.desc(), rows.c.bus_id)
            .limit(RANKING_LIMIT)
        )
        return stmt

    def _buses_visitas(self, filters):
        rows = self.queries.filtered(filters.model_copy(update={"meses": [], "anios": []})).cte("dash_attention_orders")
        episodes = self.relations.attentions
        count = func.count(rows.c.id)
        return (
            select(rows.c.bus_id, B.c.n_bus, count.label("cantidad"))
            .select_from(rows.join(episodes, episodes.c.solicitud_id == rows.c.id).join(B, B.c.id == rows.c.bus_id))
            .where(rows.c.es_ot.is_(True), MonthKey(episodes.c.fecha_atencion).in_(filters.periodos) if filters.periodos else literal(True))
            .group_by(rows.c.bus_id, B.c.n_bus)
            .order_by(count.desc(), rows.c.bus_id)
            .limit(RANKING_LIMIT)
        )

    def _talleres(self, filters):
        rows = self._workshop_rows(filters).cte("dash_workshop_orders")
        total = (
            select(func.count())
            .select_from(rows)
            .where(rows.c.grupo_taller.is_not(None), rows.c.es_ot.is_(True), rows.c.estado.in_(["EN_REPARACION", "LIBERADO", "FINALIZADO"]))
            .scalar_subquery()
        )
        parts = []
        for index, group in enumerate(WORKSHOP_GROUPS):
            count = (
                select(func.count())
                .select_from(rows)
                .where(rows.c.grupo_taller == group, rows.c.es_ot.is_(True), rows.c.estado.in_(["EN_REPARACION", "LIBERADO", "FINALIZADO"]))
                .scalar_subquery()
            )
            parts.append(
                select(
                    literal(group).label("grupo"),
                    count.label("cantidad"),
                    percentage(count, total).label("porcentaje"),
                    literal(index).label("orden"),
                )
            )
        groups = union_all(*parts).subquery()
        return select(groups.c.grupo, groups.c.cantidad, groups.c.porcentaje).order_by(
            groups.c.orden
        )

    async def workshop_coverage(self, filters):
        rows = self._workshop_rows(filters).cte("dash_workshop_coverage")
        return await self.one(
            select(
                count_when(rows.c.grupo_taller.is_not(None)).label("ot_clasificadas"),
                count_when(rows.c.ubicacion_id.is_(None)).label("ot_sin_ubicacion"),
                count_when(rows.c.ubicacion_id.is_not(None) & rows.c.grupo_taller.is_(None)).label(
                    "ot_no_clasificables"
                ),
            ).select_from(rows)
        )

    async def external_workshops(self, filters):
        rows = (
            self._workshop_rows(filters)
            .where(self.relations.orders.c.grupo_taller == "EXTERNOS")
            .cte("dash_external_orders")
        )
        total = select(func.count()).select_from(rows).scalar_subquery()
        stmt = (
            select(
                rows.c.taller_nombre_snapshot.label("nombre_snapshot"),
                rows.c.ciudad_nombre_snapshot.label("ciudad_snapshot"),
                func.count().label("ot"),
                percentage(func.count(), total).label("porcentaje_del_total_externo"),
            )
            .group_by(rows.c.taller_nombre_snapshot, rows.c.ciudad_nombre_snapshot)
            .order_by(
                func.count().desc(), rows.c.taller_nombre_snapshot, rows.c.ciudad_nombre_snapshot
            )
        )
        return await self.page(stmt, filters)

    def _workshop_rows(self, filters):
        orders = self.relations.orders
        episodes = self.relations.attentions
        loose = filters.model_copy(update={"meses": [], "anios": []})
        stmt = self.queries.filtered(loose).join(
            episodes, episodes.c.solicitud_id == orders.c.id
        ).where(
            orders.c.es_ot.is_(True),
            orders.c.estado.in_(["EN_REPARACION", "LIBERADO", "FINALIZADO"]),
        )
        return stmt.where(MonthKey(episodes.c.fecha_atencion).in_(filters.periodos)) if filters.periodos else stmt
