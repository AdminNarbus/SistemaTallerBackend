"""Composición de WHERE compartida por listados, gráficos y métricas."""

from sqlalchemy import Integer, String, and_, case, cast, exists, func, select, union

from app.modules.dashboard.constants import AGE_GROUPS
from app.modules.dashboard.repository.relations import D, V
from app.modules.dashboard.repository.sql_expressions import (
    BusKey,
    EndOfDay,
    Hours,
    LocalDay,
    MonthKey,
    WeekKey,
)


def conditions(orders, filters):
    c, result = orders.c, []
    values = (("bus_id", c.bus_id), ("solicitud_id", c.id), ("n_bus", BusKey(c.n_bus)))
    result.extend(
        column == getattr(filters, name)
        for name, column in values
        if getattr(filters, name, None) is not None
    )
    if filters.estados:
        result.append(c.estado.in_(filters.estados))
    if filters.meses:
        result.append(cast(func.substr(c.periodo, 6, 2), Integer).in_(filters.meses))
    if filters.anios:
        result.append(cast(func.substr(c.periodo, 1, 4), Integer).in_(filters.anios))
    return result


class OrderQueries:
    def __init__(self, relations):
        self.r = relations
        self.o = relations.orders

    def filtered(self, filters):
        clauses = conditions(self.o, filters)
        if filters.mecanicos_ids:
            p = self.r.participants.c
            clauses.append(
                exists(
                    select(1).where(
                        p.solicitud_id == self.o.c.id, p.mecanico_id.in_(filters.mecanicos_ids)
                    )
                )
            )
        return select(self.o).where(*clauses)

    def chart(self, filters):
        stmt = self.filtered(filters)
        if filters.periodos:
            stmt = stmt.where(self.o.c.periodo.in_(filters.periodos))
        return stmt

    def latest(self, filters):
        loose = filters.model_copy(update={"estados": [], "meses": [], "anios": []})
        base = (
            self.filtered(loose)
            .where(self.o.c.bus_activo.is_(True), self.o.c.bus_id.is_not(None))
            .cte("dash_latest_candidates")
        )
        ranked = select(
            base,
            func.row_number()
            .over(
                partition_by=base.c.bus_id,
                order_by=(base.c.fecha_creacion.desc(), base.c.id.desc()),
            )
            .label("rn"),
        ).cte("dash_latest_ranked")
        stmt = select(ranked).where(ranked.c.rn == 1)
        if filters.estados:
            stmt = stmt.where(ranked.c.estado.in_(filters.estados))
        if filters.meses:
            stmt = stmt.where(cast(func.substr(ranked.c.periodo, 6, 2), Integer).in_(filters.meses))
        if filters.anios:
            stmt = stmt.where(cast(func.substr(ranked.c.periodo, 1, 4), Integer).in_(filters.anios))
        return stmt

    def open_latest(self, filters):
        latest = self.latest(filters).cte("dash_current_orders")
        stmt = select(latest).where(
            latest.c.fecha_termino.is_(None),
            ((latest.c.es_ot.is_(False)) | latest.c.estado.in_(["PENDIENTE", "EN_REPARACION"]))
        )
        periods = getattr(filters, "seleccion_periodos", []) or getattr(filters, "periodos", [])
        return stmt.where(latest.c.periodo.in_(periods)) if periods else stmt

    def cutoff(self):
        return select(func.max(LocalDay(self.o.c.fecha_creacion))).scalar_subquery()

    def age_group(self, orders):
        days = Hours(orders.c.fecha_creacion, func.now()) / 24
        return case((days <= 7, AGE_GROUPS[0]), (days <= 28, AGE_GROUPS[1]), else_=AGE_GROUPS[2])

    def selected(self, filters):
        stmt = self._chart_selection(filters)
        return stmt.where(*self._table_conditions(filters))

    def _chart_selection(self, filters):
        if filters.seleccion_tipo == "antiguedad":
            aged = self.open_latest(filters).cte("dash_selected_aging")
            ids = select(aged.c.id).where(self.age_group(aged) == filters.seleccion_grupo)
            return select(self.o).where(self.o.c.id.in_(ids))
        event_selection = filters.seleccion_tipo in {"taller", "mecanico", "bus_fallas", "bus_visitas", "creadas", "terminadas", "visitas_bus"}
        stmt = self.filtered(filters.model_copy(update={"meses": [], "anios": []})) if event_selection else self.chart(filters)
        if filters.seleccion_periodos and not event_selection:
            stmt = stmt.where(self.o.c.periodo.in_(filters.seleccion_periodos))
        clause = self._selection_condition(filters)
        return stmt.where(clause) if clause is not None else stmt

    def _selection_condition(self, filters):
        c, kind = self.o.c, filters.seleccion_tipo
        if kind == "taller":
            episode = self.r.attentions.c
            return and_(
                c.grupo_taller == filters.seleccion_grupo,
                c.es_ot.is_(True),
                c.estado.in_(["EN_REPARACION", "LIBERADO", "FINALIZADO"]),
                exists(select(1).where(
                    episode.solicitud_id == c.id,
                    MonthKey(episode.fecha_atencion).in_(filters.seleccion_periodos) if filters.seleccion_periodos else True,
                )),
            )
        if kind == "mecanico":
            participants = self.r.fault_participants
            attended_faults = self.r.attended_faults
            p = participants.c
            attended = attended_faults.c
            return exists(
                select(1).select_from(participants.join(attended_faults, attended.detalle_id == p.detalle_id)).where(
                    p.solicitud_id == c.id, p.mecanico_id == filters.seleccion_mecanico_id,
                    MonthKey(attended.fecha_atencion).in_(filters.seleccion_periodos) if filters.seleccion_periodos else True,
                )
            )
        if kind in {"bus_fallas", "bus_visitas", "visitas_bus"}:
            clause = c.bus_id == filters.seleccion_bus_id
            if kind == "bus_fallas":
                return and_(clause, exists(select(1).where(
                    D.c.solicitud_id == c.id,
                    MonthKey(func.coalesce(D.c.fecha_reporte, D.c.fecha_creacion)).in_(filters.seleccion_periodos) if filters.seleccion_periodos else True,
                )))
            episode = self.r.attentions.c
            return and_(clause, c.es_ot.is_(True), exists(select(1).where(
                episode.solicitud_id == c.id,
                MonthKey(episode.fecha_atencion).in_(filters.seleccion_periodos) if filters.seleccion_periodos else True,
            )))
        if kind in {"creadas", "terminadas"}:
            value = filters.seleccion_semana.isoformat()
            return (
                WeekKey(c.fecha_creacion) == value
                if kind == "creadas"
                else and_(
                    WeekKey(c.fecha_termino) == value,
                )
            )
        if kind == "reincidencias_bus":
            return self._recurrence_selection(filters)
        return None

    def _recurrence_selection(self, filters):
        posterior = self.filtered(filters).cte("dash_recurrence_visible")
        r = self.r.recurrences.c
        pairs = (
            select(self.r.recurrences)
            .join(posterior, posterior.c.id == r.solicitud_id)
            .where(r.bus_id == filters.seleccion_bus_id, r.periodo == filters.seleccion_periodo)
            .cte("dash_selected_pairs")
        )
        ids = union(select(pairs.c.solicitud_id), select(pairs.c.anterior_ot))
        return and_(self.o.c.bus_id == filters.seleccion_bus_id, self.o.c.id.in_(ids))

    def _table_conditions(self, filters):
        c, clauses = self.o.c, []
        if filters.tabla_n_bus:
            clauses.append(BusKey(c.n_bus).startswith(filters.tabla_n_bus, autoescape=True))
        if filters.tabla_ot:
            clauses.append(cast(c.id, String).startswith(filters.tabla_ot, autoescape=True))
        if filters.tabla_estados:
            clauses.append(c.estado.in_(filters.tabla_estados))
        if filters.tabla_periodos:
            clauses.append(c.periodo.in_(filters.tabla_periodos))
        if filters.tabla_anios:
            clauses.append(cast(func.substr(c.periodo, 1, 4), Integer).in_(filters.tabla_anios))
        return clauses
