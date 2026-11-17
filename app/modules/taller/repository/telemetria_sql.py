"""Expresiones SQL para agregar permanencia física sin cargar entidades."""
from sqlalchemy import case, func, select

from app.modules.taller.models.taller_solicitud import TallerSolicitud as OT
from app.modules.taller.models.taller_solicitud_estadia import TallerSolicitudEstadia as Estadia


def horas_taller_por_solicitud(db):
    activo = OT.estado == "EN_REPARACION"
    fin = case(
        (OT.estado == "LIBERADO", func.coalesce(OT.fecha_liberacion, OT.fecha_cierre)),
        (OT.estado == "FINALIZADO", func.coalesce(OT.fecha_cierre, OT.fecha_liberacion)),
        else_=None,
    )
    referencia = case((activo, func.current_timestamp()), else_=fin)

    def duracion(inicio, salida):
        if db.bind.dialect.name == "sqlite":
            horas = (func.julianday(salida) - func.julianday(inicio)) * 24
        else:
            horas = func.extract("epoch", salida - inicio) / 3600
        return case((horas > 0, horas), else_=0.0)

    horas_visita = func.coalesce(
        Estadia.horas_estadia,
        duracion(Estadia.fecha_ingreso, func.coalesce(Estadia.fecha_salida, referencia)),
    )
    visitas = select(func.sum(horas_visita)).where(
        Estadia.solicitud_id == OT.id
    ).correlate(OT).scalar_subquery()
    legado = case(
        (OT.horas_taller_acumuladas > 0, OT.horas_taller_acumuladas),
        else_=duracion(OT.fecha_primer_ingreso_taller, referencia),
    )
    return func.coalesce(visitas, legado, 0.0)
