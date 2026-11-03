from sqlalchemy import (
    Integer,
    String,
    and_,
    case,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
    union_all,
)

from app.modules.dashboard.repository.base import ReadRepository, count_when
from app.modules.dashboard.repository.relations import C, D, E, EM, SE, U, fault_description, full_name
from app.modules.dashboard.repository.sql_expressions import MonthKey


class CronologiaRepository(ReadRepository):
    def milestones(self, request):
        bus_id, filters = request
        statement = self.queries.filtered(filters.model_copy(update={"meses": [], "anios": [], "estados": []}))
        if bus_id is not None:
            statement = statement.where(self.relations.orders.c.bus_id == bus_id)
        rows = statement.cte("dash_timeline_orders")
        recorded = self._recorded(rows)
        all_stages = union_all(select(recorded), *self._derived(rows, recorded)).cte(
            "dash_all_stages"
        )
        statement = select(all_stages)
        if filters.hito_meses:
            statement = statement.where(
                cast(func.substr(MonthKey(all_stages.c.fecha_evento), 6, 2), Integer).in_(
                    filters.hito_meses
                )
            )
        if filters.hito_anios:
            statement = statement.where(
                cast(func.substr(MonthKey(all_stages.c.fecha_evento), 1, 4), Integer).in_(
                    filters.hito_anios
                )
            )
        return statement.cte("dash_visible_stages")

    def _recorded(self, rows):
        new_flow = or_(rows.c.es_ot.is_(False), rows.c.fecha_aprobacion_verificada.is_not(None))
        return (
            select(
                (literal("evento:") + cast(SE.c.id, String)).label("hito_id"),
                rows.c.id.label("solicitud_id"),
                case((and_(SE.c.tipo_evento == "CREACION", new_flow), "SOLICITUD"), else_=SE.c.tipo_evento).label("tipo_evento"),
                SE.c.fecha_evento,
                SE.c.estado_anterior,
                case((and_(SE.c.tipo_evento == "CREACION", new_flow), "SOLICITADO"), else_=SE.c.estado_nuevo).label("estado_nuevo"),
                literal(False).label("derivado"),
                full_name(U).label("creador_nombre"),
                SE.c.id.label("sort_id"),
            )
            .select_from(
                SE.join(rows, rows.c.id == SE.c.solicitud_id).outerjoin(
                    U, U.c.id == rows.c.usuario_creador_id
                )
            )
            .where(SE.c.estado_nuevo.is_not(None))
            .cte("dash_recorded_stages")
        )

    def _derived(self, rows, recorded):
        specs = (
            ("CREACION", "SOLICITADO", None, rows.c.fecha_creacion),
            (
                "EN_REPARACION",
                "EN_REPARACION",
                literal("PENDIENTE"),
                rows.c.fecha_primer_ingreso_taller,
            ),
            ("LIBERADO", "LIBERADO", literal("EN_REPARACION"), rows.c.fecha_liberacion),
            ("FINALIZADO", "FINALIZADO", self._previous_final(rows), rows.c.fecha_cierre),
        )
        legacy_creation = self._derived_stage((rows, recorded), ("CREACION_LEGACY", "PENDIENTE", None, rows.c.fecha_creacion))
        return [self._derived_stage((rows, recorded), spec) for spec in specs] + [legacy_creation, self._approval_stage(rows)]

    def _approval_stage(self, rows):
        actor = (
            select(full_name(U))
            .select_from(C.join(U, U.c.id == C.c.usuario_id))
            .where(
                C.c.solicitud_id == rows.c.id,
                C.c.tipo == "SISTEMA",
                C.c.comentario.startswith("Solicitud aprobada como OT."),
            )
            .order_by(C.c.fecha_registro, C.c.id)
            .limit(1)
            .correlate(rows)
            .scalar_subquery()
        )
        return (
            select(
                (literal("aprobacion:") + cast(rows.c.id, String)).label("hito_id"),
                rows.c.id.label("solicitud_id"),
                literal("CREACION_OT").label("tipo_evento"),
                rows.c.fecha_aprobacion_verificada.label("fecha_evento"),
                literal("SOLICITADO").label("estado_anterior"),
                literal("PENDIENTE").label("estado_nuevo"),
                literal(False).label("derivado"),
                actor.label("creador_nombre"),
                literal(1).label("sort_id"),
            )
            .where(rows.c.fecha_aprobacion_verificada.is_not(None))
        )

    def _previous_final(self, rows):
        state = (
            select(SE.c.estado_nuevo)
            .where(
                SE.c.solicitud_id == rows.c.id,
                SE.c.fecha_evento <= rows.c.fecha_cierre,
                SE.c.estado_nuevo.is_not(None),
                SE.c.estado_nuevo != "FINALIZADO",
                SE.c.tipo_evento != "CREACION",
            )
            .order_by(SE.c.fecha_evento.desc(), SE.c.id.desc())
            .limit(1)
            .correlate(rows)
            .scalar_subquery()
        )
        return func.coalesce(
            state, case((rows.c.fecha_liberacion.is_not(None), "LIBERADO"), else_="EN_REPARACION")
        )

    def _derived_stage(self, context, spec):
        rows, recorded = context
        key, state, previous, date = spec
        match = (
            recorded.c.tipo_evento.in_(["CREACION", "SOLICITUD"])
            if key in {"CREACION", "CREACION_LEGACY"}
            else and_(recorded.c.estado_nuevo == state, recorded.c.tipo_evento != "CREACION")
        )
        missing = ~exists(select(1).where(recorded.c.solicitud_id == rows.c.id, match))
        return (
            select(
                (literal("derivado:") + cast(rows.c.id, String) + ":" + key).label("hito_id"),
                rows.c.id.label("solicitud_id"),
                literal("SOLICITUD" if key == "CREACION" else "CREACION" if key == "CREACION_LEGACY" else "CAMBIO_ESTADO").label("tipo_evento"),
                date.label("fecha_evento"),
                (previous if previous is not None else cast(literal(None), String)).label(
                    "estado_anterior"
                ),
                literal(state).label("estado_nuevo"),
                literal(True).label("derivado"),
                full_name(U).label("creador_nombre"),
                literal(0).label("sort_id"),
            )
            .select_from(rows.outerjoin(U, U.c.id == rows.c.usuario_creador_id))
            .where(
                date.is_not(None), missing,
                or_(key not in {"CREACION", "CREACION_LEGACY"},
                    (rows.c.es_ot.is_(False) | rows.c.fecha_aprobacion_verificada.is_not(None)) if key == "CREACION" else (rows.c.es_ot.is_(True) & rows.c.fecha_aprobacion_verificada.is_(None))),
            )
        )

    async def timeline(self, request):
        _, filters = request
        stages = self.milestones(request)
        fields = [column for column in stages.c if column.name != "sort_id"]
        stmt = select(*fields).order_by(
            stages.c.fecha_evento.desc(),
            stages.c.solicitud_id.desc(),
            stages.c.sort_id.desc(),
            stages.c.hito_id,
        )
        return await self.page(stmt, filters)

    async def has_milestone(self, request):
        _, filters = request
        stages = self.milestones(request)
        rows = await self.rows(
            select(stages.c.hito_id).where(stages.c.hito_id == filters.hito_id).limit(1)
        )
        return bool(rows)

    def historical_rows(self, request):
        stages = self.milestones(request)
        date = func.coalesce(D.c.fecha_reporte, D.c.fecha_creacion)
        event = (
            select(E.c.id)
            .where(
                E.c.detalle_id == D.c.id,
                E.c.fecha_evento <= stages.c.fecha_evento,
                E.c.estado_nuevo.is_not(None),
            )
            .order_by(E.c.fecha_evento.desc(), E.c.id.desc())
            .limit(1)
            .correlate(stages, D)
            .scalar_subquery()
        )
        known_before = exists(
            select(1).where(E.c.detalle_id == D.c.id, E.c.fecha_evento <= stages.c.fecha_evento)
        ).correlate(stages, D)
        source = stages.outerjoin(
            D,
            and_(
                D.c.solicitud_id == stages.c.solicitud_id,
                or_(date <= stages.c.fecha_evento, known_before),
            ),
        )
        evidence = (
            select(
                stages,
                D.c.id.label("detalle_id"),
                fault_description().label("descripcion"),
                date.label("fecha_reporte"),
                D.c.reportado_por_id,
                event.label("evento_falla_id"),
            )
            .select_from(source)
            .cte("dash_stage_evidence")
        )
        return self._historical_state(evidence)

    def _historical_state(self, evidence):
        state = func.coalesce(
            E.c.estado_nuevo,
            case(
                (
                    and_(
                        evidence.c.tipo_evento.in_(["CREACION", "SOLICITUD"]),
                        evidence.c.detalle_id.is_not(None),
                        evidence.c.fecha_reporte <= evidence.c.fecha_evento,
                    ),
                    "PENDIENTE",
                ),
                else_=None,
            ),
        )
        return (
            select(
                evidence.c.solicitud_id,
                evidence.c.hito_id,
                evidence.c.tipo_evento,
                evidence.c.fecha_evento,
                evidence.c.estado_nuevo.label("estado_ot"),
                evidence.c.creador_nombre,
                evidence.c.detalle_id,
                case(
                    (evidence.c.detalle_id.is_not(None), evidence.c.descripcion), else_=None
                ).label("descripcion"),
                evidence.c.fecha_reporte,
                full_name(U).label("reportante_nombre"),
                state.label("estado_falla"),
                evidence.c.evento_falla_id,
                evidence.c.sort_id,
            )
            .select_from(
                evidence.outerjoin(E, E.c.id == evidence.c.evento_falla_id).outerjoin(
                    U, U.c.id == evidence.c.reportado_por_id
                )
            )
            .cte("dash_historical_faults")
        )

    async def details(self, request):
        _, filters = request
        rows = self.historical_rows(request)
        stmt = select(rows)
        if filters.hito_id:
            stmt = stmt.where(rows.c.hito_id == filters.hito_id)
        stmt = stmt.order_by(
            rows.c.solicitud_id.desc(),
            rows.c.fecha_evento.desc(),
            rows.c.sort_id.desc(),
            rows.c.hito_id,
            rows.c.estado_falla,
            rows.c.descripcion,
            rows.c.detalle_id,
        )
        return await self.page(stmt, filters)

    async def authors(self, event_ids):
        name = func.coalesce(
            func.nullif(func.trim(EM.c.mecanico_nombre_snapshot), ""), full_name(U)
        )
        stmt = (
            select(EM.c.evento_id, name.label("nombre"))
            .outerjoin(U, U.c.id == EM.c.mecanico_id)
            .where(EM.c.evento_id.in_(event_ids), name.is_not(None))
            .distinct()
            .order_by(EM.c.evento_id, name)
        )
        return await self.rows(stmt) if event_ids else []

    async def summary(self, request):
        rows = self.historical_rows(request)
        ranked = (
            select(
                rows.c.detalle_id,
                rows.c.estado_falla,
                func.row_number()
                .over(
                    partition_by=rows.c.detalle_id,
                    order_by=(rows.c.fecha_evento.desc(), rows.c.sort_id.desc(), rows.c.hito_id),
                )
                .label("rn"),
            )
            .where(rows.c.detalle_id.is_not(None))
            .cte("dash_last_visible_fault")
        )
        latest = select(ranked).where(ranked.c.rn == 1).cte("dash_export_faults")
        orders = self.relations.orders
        visible_orders = rows.join(orders, orders.c.id == rows.c.solicitud_id)
        ot = select(func.count(func.distinct(rows.c.solicitud_id))).select_from(visible_orders).where(
            orders.c.es_ot.is_(True)
        ).scalar_subquery()
        solicitudes = select(func.count(func.distinct(rows.c.solicitud_id))).scalar_subquery()
        fields = [
            count_when(latest.c.estado_falla == state).label(label)
            for state, label in (
                ("RESUELTA", "resueltas"),
                ("PENDIENTE", "pendientes"),
                ("INCOMPLETA", "incompletas"),
            )
        ]
        return await self.one(
            select(
                ot.label("ot_distintas"),
                solicitudes.label("solicitudes_distintas"),
                func.count().label("fallas_distintas"),
                *fields,
                count_when(latest.c.estado_falla.is_(None)).label("sin_estado_documentado")
            ).select_from(latest)
        )
