"""Relaciones comunes, sin cargar entidades ORM ni disparar lazy loading."""

from sqlalchemy import and_, case, func, literal, select, union, union_all

from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.buses.models.bus import Bus
from app.modules.dashboard.constants import RECURRENCE_HOURS
from app.modules.dashboard.repository.sql_expressions import BusKey, Hours, MonthKey, Normalized
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.taller_falla_evento import TallerFallaEvento
from app.modules.taller.models.taller_falla_evento_mecanico import TallerFallaEventoMecanico
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_solicitud_estadia import TallerSolicitudEstadia
from app.modules.taller.models.taller_solicitud_estado_evento import TallerSolicitudEstadoEvento
from app.modules.taller.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.taller.models.taller_ubicacion import TallerResultadoUbicacion

B = Bus.__table__
U = Usuario.__table__
R = Rol.__table__
S = TallerSolicitud.__table__
C = TallerSolicitudComentario.__table__
D = TallerSolicitudDetalle.__table__
A = TallerAsignacionFalla.__table__
M = TallerSolicitudMecanico.__table__
E = TallerFallaEvento.__table__
EM = TallerFallaEventoMecanico.__table__
SE = TallerSolicitudEstadoEvento.__table__
V = TallerSolicitudEstadia.__table__
L = TallerResultadoUbicacion.__table__


def full_name(table):
    value = func.trim(func.coalesce(table.c.nombre, "") + " " + func.coalesce(table.c.apellido, ""))
    return func.nullif(value, "")


def fault_description():
    return func.coalesce(
        func.nullif(D.c.descripcion_personalizada, ""),
        func.nullif(D.c.falla_nombre_snapshot, ""),
        literal("Falla sin descripción"),
    )


class Relations:
    def __init__(self):
        self.mechanics = (
            select(U.c.id, full_name(U).label("nombre_completo"), U.c.is_active)
            .join(R, R.c.id == U.c.rol_id)
            .where(R.c.nombre == "MECANICO")
            .cte("dash_mechanics")
        )
        self.approval = self._approval()
        self.first_assignment = self._first_assignment()
        self.attended_faults = self._attended_faults()
        self.attentions = self._attentions()
        self.fault_participants = self._fault_participants()
        self.participants = self._participants()
        self.locations = self._locations()
        self.orders = self._orders()
        self.recurrences = self._recurrences()

    def _approval(self):
        return (
            select(
                C.c.solicitud_id,
                func.min(C.c.fecha_registro).label("fecha_creacion_ot"),
            )
            .where(
                C.c.tipo == "SISTEMA",
                C.c.comentario.startswith("Solicitud aprobada como OT."),
            )
            .group_by(C.c.solicitud_id)
            .cte("dash_ot_approval")
        )

    def _first_assignment(self):
        rows = union_all(
            select(M.c.solicitud_id, M.c.fecha_asignacion).join(
                self.mechanics, self.mechanics.c.id == M.c.mecanico_id
            ),
            select(A.c.solicitud_id, A.c.fecha_asignacion).join(
                self.mechanics, self.mechanics.c.id == A.c.mecanico_id
            ),
        ).subquery()
        return (
            select(
                rows.c.solicitud_id, func.min(rows.c.fecha_asignacion).label("primera_asignacion")
            )
            .group_by(rows.c.solicitud_id)
            .cte("dash_first_assignment")
        )

    def _attended_faults(self):
        events = union_all(
            select(E.c.detalle_id, E.c.fecha_evento.label("fecha_atencion")).where(
                E.c.estado_nuevo.in_(["RESUELTA", "INCOMPLETA"])
            ),
            select(D.c.id, func.coalesce(D.c.fecha_resolucion, D.c.fecha_cambio_estado)).where(
                D.c.estado.in_(["RESUELTA", "INCOMPLETA"]),
                func.coalesce(D.c.fecha_resolucion, D.c.fecha_cambio_estado).is_not(None),
            ),
        ).subquery()
        return (
            select(events.c.detalle_id, func.min(events.c.fecha_atencion).label("fecha_atencion"))
            .group_by(events.c.detalle_id)
            .cte("dash_attended_faults")
        )

    def _attentions(self):
        events = union_all(
            select(V.c.solicitud_id, V.c.fecha_ingreso.label("fecha_atencion")),
            select(SE.c.solicitud_id, SE.c.fecha_evento).where(
                SE.c.estado_nuevo.in_(["EN_REPARACION", "LIBERADO", "FINALIZADO"])
            ),
            select(S.c.id, S.c.fecha_primer_ingreso_taller).where(S.c.fecha_primer_ingreso_taller.is_not(None)),
            select(S.c.id, S.c.fecha_liberacion).where(S.c.fecha_liberacion.is_not(None)),
            select(S.c.id, S.c.fecha_cierre).where(S.c.fecha_cierre.is_not(None)),
        ).subquery()
        return (
            select(events.c.solicitud_id, func.min(events.c.fecha_atencion).label("fecha_atencion"))
            .group_by(events.c.solicitud_id)
            .cte("dash_attention_episodes")
        )

    def _fault_participants(self):
        rows = union(
            select(D.c.id.label("detalle_id"), D.c.solicitud_id, M.c.mecanico_id).join(
                M, M.c.solicitud_id == D.c.solicitud_id
            ),
            select(A.c.detalle_id, A.c.solicitud_id, A.c.mecanico_id),
            select(D.c.id, D.c.solicitud_id, D.c.mecanico_resolvio_id),
            select(D.c.id, D.c.solicitud_id, EM.c.mecanico_id)
            .join(E, E.c.detalle_id == D.c.id)
            .join(EM, EM.c.evento_id == E.c.id),
        ).subquery()
        return (
            select(rows)
            .join(self.mechanics, self.mechanics.c.id == rows.c.mecanico_id)
            .cte("dash_fault_participants")
        )

    def _participants(self):
        rows = union(
            select(M.c.solicitud_id, M.c.mecanico_id),
            select(self.fault_participants.c.solicitud_id, self.fault_participants.c.mecanico_id),
        ).subquery()
        return (
            select(rows)
            .join(self.mechanics, self.mechanics.c.id == rows.c.mecanico_id)
            .cte("dash_participants")
        )

    def _locations(self):
        ranked = (
            select(
                D.c.solicitud_id,
                L.c.id,
                L.c.taller_nombre_snapshot,
                L.c.ciudad_nombre_snapshot,
                L.c.taller_tipo_snapshot,
                func.row_number()
                .over(
                    partition_by=D.c.solicitud_id,
                    order_by=(L.c.registrado_en.desc(), L.c.id.desc()),
                )
                .label("rn"),
            )
            .select_from(L.join(E, E.c.id == L.c.evento_id).join(D, D.c.id == E.c.detalle_id))
            .cte("dash_location_ranked")
        )
        city = func.lower(func.trim(ranked.c.ciudad_nombre_snapshot))
        group = case(
            (ranked.c.taller_tipo_snapshot == "EXTERNO", "EXTERNOS"),
            (and_(ranked.c.taller_tipo_snapshot == "INTERNO", city == "temuco"), "INTERNO_TEMUCO"),
            (
                and_(ranked.c.taller_tipo_snapshot == "INTERNO", city == "santiago"),
                "INTERNO_SANTIAGO",
            ),
            else_=None,
        )
        return (
            select(ranked, group.label("grupo_taller"))
            .where(ranked.c.rn == 1)
            .cte("dash_locations")
        )

    def _bus_fallback(self):
        return (
            select(BusKey(B.c.n_bus).label("clave"), func.min(B.c.id).label("id"))
            .group_by(BusKey(B.c.n_bus))
            .having(func.count() == 1)
            .cte("dash_bus_fallback")
        )

    def _effective_state(self):
        latest = (
            select(SE.c.estado_nuevo)
            .where(SE.c.solicitud_id == S.c.id, SE.c.estado_nuevo.is_not(None))
            .order_by(SE.c.fecha_evento.desc(), SE.c.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        return func.coalesce(latest, S.c.estado)

    def _end(self):
        recorded = (
            select(func.min(SE.c.fecha_evento))
            .where(SE.c.solicitud_id == S.c.id, SE.c.estado_nuevo.in_(["LIBERADO", "FINALIZADO"]))
            .correlate(S)
            .scalar_subquery()
        )
        legacy = case(
            (S.c.fecha_liberacion.is_(None), S.c.fecha_cierre),
            (S.c.fecha_cierre.is_(None), S.c.fecha_liberacion),
            (S.c.fecha_liberacion < S.c.fecha_cierre, S.c.fecha_liberacion),
            else_=S.c.fecha_cierre,
        )
        return func.coalesce(recorded, legacy)

    def _orders(self):
        fallback = self._bus_fallback()
        bus_id = func.coalesce(S.c.bus_id, fallback.c.id)
        source = (
            S.outerjoin(fallback, BusKey(S.c.n_bus) == fallback.c.clave)
            .outerjoin(B, B.c.id == bus_id)
            .outerjoin(self.approval, self.approval.c.solicitud_id == S.c.id)
            .outerjoin(self.first_assignment, self.first_assignment.c.solicitud_id == S.c.id)
            .outerjoin(self.locations, self.locations.c.solicitud_id == S.c.id)
        )
        first, end = self.first_assignment.c.primera_asignacion, self._end()
        ot_start = case(
            (S.c.es_ot.is_(True), func.coalesce(self.approval.c.fecha_creacion_ot, S.c.fecha_creacion)),
            else_=None,
        )
        return (
            select(
                S.c.id,
                S.c.n_bus,
                bus_id.label("bus_id"),
                B.c.is_active.label("bus_activo"),
                case((S.c.es_ot.is_(False), "SOLICITADO"), else_=self._effective_state()).label("estado"),
                S.c.fecha_creacion,
                S.c.es_ot,
                ot_start.label("fecha_creacion_ot"),
                self.approval.c.fecha_creacion_ot.label("fecha_aprobacion_verificada"),
                S.c.fecha_cierre,
                S.c.fecha_liberacion,
                S.c.fecha_primer_ingreso_taller,
                S.c.usuario_creador_id,
                end.label("fecha_termino"),
                first,
                MonthKey(S.c.fecha_creacion).label("periodo"),
                Hours(S.c.fecha_creacion, self.approval.c.fecha_creacion_ot).label("respuesta_raw"),
                Hours(first, end).label("reparacion_raw"),
                Hours(ot_start, end).label("completo_raw"),
                Hours(S.c.fecha_creacion, end).label("total_raw"),
                self.locations.c.id.label("ubicacion_id"),
                self.locations.c.grupo_taller,
                self.locations.c.taller_nombre_snapshot,
                self.locations.c.ciudad_nombre_snapshot,
            )
            .select_from(source)
            .cte("dash_orders")
        )

    def _recurrences(self):
        date = func.coalesce(D.c.fecha_reporte, D.c.fecha_creacion)
        key = Normalized(D.c.descripcion_personalizada)
        window = {"partition_by": (self.orders.c.bus_id, key), "order_by": (date, D.c.id)}
        reports = (
            select(
                D.c.id.label("detalle_id"),
                D.c.solicitud_id,
                self.orders.c.bus_id,
                date.label("fecha_reporte"),
                MonthKey(date).label("periodo"),
                func.lag(date).over(**window).label("anterior_fecha"),
                func.lag(D.c.solicitud_id).over(**window).label("anterior_ot"),
            )
            .select_from(D.join(self.orders, self.orders.c.id == D.c.solicitud_id))
            .where(self.orders.c.bus_id.is_not(None), self.orders.c.es_ot.is_(True), key.is_not(None))
            .cte("dash_report_history")
        )
        difference = Hours(reports.c.anterior_fecha, reports.c.fecha_reporte)
        return (
            select(reports)
            .where(difference >= 0, difference <= RECURRENCE_HOURS)
            .cte("dash_recurrences")
        )
