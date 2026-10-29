from sqlalchemy import case, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models.usuario import Usuario
from app.modules.buses.models.bus import Bus
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle


class BusesTallerRepository:
    """Consulta de buses y su OT vigente, sin cargar relaciones ORM por bus."""

    async def listar(self, db: AsyncSession, filtros: dict) -> list[dict]:
        coincidencias = self._consulta_buses(filtros).cte("buses_coincidentes")
        total = select(func.count().label("total")).select_from(coincidencias).cte("total_buses")
        orden = (coincidencias.c.prioridad, coincidencias.c.n_bus, coincidencias.c.bus_id)
        pagina = (select(coincidencias).order_by(*orden)
                  .offset(filtros["skip"]).limit(filtros["limit"]).cte("pagina_buses"))
        consulta = (select(pagina, total.c.total)
                    .select_from(total.outerjoin(pagina, true()))
                    .order_by(pagina.c.prioridad, pagina.c.n_bus, pagina.c.bus_id))
        resultado = await db.execute(consulta)
        return [dict(fila) for fila in resultado.mappings()]

    def _consulta_buses(self, filtros: dict):
        ot = TallerSolicitud
        fallas = self._conteo_fallas()
        prioridad = case(
            (ot.es_ot.is_(True) & ot.estado.in_(("PENDIENTE", "EN_REPARACION")), 0),
            (ot.es_ot.is_(True) & (ot.estado == "LIBERADO"), 1),
            (ot.id.is_not(None), 2), else_=3,
        )
        consulta = select(
            Bus.id.label("bus_id"), Bus.n_bus, ot.id.label("ot_id"), ot.estado.label("ot_estado"),
            ot.es_ot, ot.fecha_creacion, self._nombre_creador().label("creador_nombre"),
            func.coalesce(fallas.c.pendientes, 0).label("numero_fallas_pendientes"),
            prioridad.label("prioridad"),
        ).outerjoin(ot, ot.id == self._ot_vigente()).outerjoin(
            Usuario, Usuario.id == ot.usuario_creador_id,
        ).outerjoin(fallas, fallas.c.solicitud_id == ot.id)
        if filtros["solo_activos"]:
            consulta = consulta.where(Bus.is_active.is_(True))
        if filtros.get("q"):
            consulta = consulta.where(or_(Bus.n_bus.icontains(filtros["q"], autoescape=True),
                                          Bus.patente.icontains(filtros["q"], autoescape=True)))
        return consulta

    def _nombre_creador(self):
        nombre = func.nullif(Usuario.nombre, "")
        apellido = func.nullif(Usuario.apellido, "")
        return case(
            (nombre.is_not(None) & apellido.is_not(None), nombre + " " + apellido),
            (nombre.is_not(None), nombre),
            else_=Usuario.username,
        )

    def _ot_vigente(self):
        ot = TallerSolicitud
        identidad = or_(ot.bus_id == Bus.id,
                        (ot.bus_id.is_(None)) & (func.lower(func.trim(ot.n_bus)) == func.lower(func.trim(Bus.n_bus))))
        return (select(ot.id).where(ot.estado != "FINALIZADO", identidad)
                .order_by(case((ot.bus_id.is_not(None), 0), else_=1), ot.fecha_creacion, ot.id)
                .limit(1).correlate(Bus).scalar_subquery())

    def _conteo_fallas(self):
        detalle = TallerSolicitudDetalle
        return (select(detalle.solicitud_id, func.count().label("pendientes"))
                .where(detalle.estado.in_(("PENDIENTE", "INCOMPLETA")))
                .group_by(detalle.solicitud_id).subquery())


buses_taller_repository = BusesTallerRepository()
