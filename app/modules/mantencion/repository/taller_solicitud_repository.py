from typing import Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud


class TallerSolicitudRepository:
    """Repositorio para la persistencia de solicitudes de mantención en taller."""

    async def crear_solicitud(
        self,
        db: AsyncSession,
        n_bus: str,
        usuario_id: Optional[int] = None,
        id_bus: Optional[int] = None,
        descripcion: Optional[str] = None,
        items: Optional[List[Any]] = None,
        foto_url: Optional[str] = None,
        estado: Optional[str] = "PENDIENTE",
    ) -> TallerSolicitud:
        if id_bus is None and n_bus and str(n_bus).strip():
            res_b = await db.execute(
                select(Bus.id).where(Bus.n_bus == str(n_bus).strip())
            )
            id_bus = res_b.scalar_one_or_none()

        solicitud = TallerSolicitud(
            usuario_id=usuario_id,
            id_bus=id_bus,
            n_bus=str(n_bus),
            descripcion=descripcion,
            items=items,
            foto_url=foto_url,
            estado=estado or "PENDIENTE",
        )

        db.add(solicitud)
        await db.commit()
        await db.refresh(solicitud)
        return solicitud


taller_solicitud_repository = TallerSolicitudRepository()
