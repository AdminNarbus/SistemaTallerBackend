import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import PermissionException
from app.modules.auth.dtos.conductor_sync_dto import ConductorSyncResponseDTO
from app.modules.auth.services.conductor_sync_service import conductor_sync_service

router = APIRouter()


def autenticar_sync(x_conductores_sync_key: Annotated[str | None, Header()] = None) -> None:
    secreto = settings.CONDUCTORES_SYNC_SECRET
    esperado = secreto.get_secret_value() if secreto else ""
    if not esperado or not secrets.compare_digest(
        (x_conductores_sync_key or "").encode(), esperado.encode()
    ):
        raise PermissionException("Credencial de sincronización inválida o servicio no configurado.")


@router.post(
    "/interno/conductores/sincronizar",
    response_model=ConductorSyncResponseDTO,
    dependencies=[Depends(autenticar_sync)],
    tags=["Tareas internas"],
)
async def sincronizar_conductores(db: AsyncSession = Depends(get_db)) -> ConductorSyncResponseDTO:
    return await conductor_sync_service.sincronizar(db)
