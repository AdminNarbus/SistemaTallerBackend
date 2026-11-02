from datetime import datetime

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.modules.buses.models.bus import Bus
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.dtos.estado_visible_dto import EstadoVisibleDTO

router = APIRouter(prefix="/publica", tags=["API pública"])


class SolicitudPublicaDTO(EstadoVisibleDTO):
    model_config = ConfigDict(from_attributes=True)

    id: int
    n_bus: str
    descripcion_general: str | None = None
    fecha_creacion: datetime
    fecha_actualizacion: datetime | None = None


class BusTallerPublicoDTO(BaseModel):
    id: int
    n_bus: str | None
    patente: str
    marca: str | None
    modelo: str | None
    en_taller: bool


@router.get("/solicitudes", response_model=list[SolicitudPublicaDTO])
async def listar_solicitudes(
    response: Response,
    db: AsyncSession = SessionDep,
):
    """Todas las solicitudes, tanto OT como no OT, en todos los estados."""
    filas = (await db.execute(select(
        TallerSolicitud.id, TallerSolicitud.n_bus, TallerSolicitud.es_ot,
        TallerSolicitud.estado, TallerSolicitud.descripcion_general,
        TallerSolicitud.fecha_creacion, TallerSolicitud.fecha_actualizacion,
    ).order_by(TallerSolicitud.id))).mappings().all()
    response.headers["X-Total-Count"] = str(len(filas))
    response.headers["Cache-Control"] = "no-store"
    return filas


@router.get("/buses-en-taller", response_model=list[BusTallerPublicoDTO])
async def listar_buses_en_taller(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = SessionDep,
):
    """Buses registrados físicamente en taller, independientemente de su OT."""
    filtro = Bus.en_taller.is_(True)
    total = await db.scalar(select(func.count()).select_from(Bus).where(filtro))
    buses = (await db.execute(select(
        Bus.id, Bus.n_bus, Bus.patente, Bus.marca, Bus.modelo, Bus.en_taller,
    ).where(filtro).order_by(Bus.id).offset(skip).limit(limit))).mappings().all()
    response.headers["X-Total-Count"] = str(total)
    response.headers["Cache-Control"] = "no-store"
    return buses
