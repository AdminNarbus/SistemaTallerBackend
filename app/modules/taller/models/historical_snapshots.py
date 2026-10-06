"""Capture catalog names once, without async relationship loading during flush."""
from sqlalchemy import event, select

from app.modules.taller.models.categoria_falla import CategoriaFalla
from app.modules.taller.models.falla_taller import FallaTaller
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle


@event.listens_for(TallerSolicitudDetalle, "before_insert")
def capturar_catalogo_historico(mapper, connection, detalle) -> None:
    if not detalle.falla_id:
        return
    statement = (
        select(FallaTaller.nombre, CategoriaFalla.nombre)
        .join(CategoriaFalla, CategoriaFalla.id == FallaTaller.categoria_id)
        .where(FallaTaller.id == detalle.falla_id)
    )
    catalogo = connection.execute(statement).first()
    if catalogo:
        detalle.falla_nombre_snapshot = catalogo[0]
        detalle.categoria_nombre_snapshot = catalogo[1]
