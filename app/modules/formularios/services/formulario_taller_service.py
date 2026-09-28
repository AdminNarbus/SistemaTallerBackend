import logging
from typing import List, Optional
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.formularios.dtos.taller_ingreso_dto import FormularioMantencionCreateDTO
from app.modules.taller.dtos.solicitud_dto import SolicitudDTO
from app.modules.taller.services.solicitud_service import (
    SolicitudService,
    solicitud_service,
)

logger = logging.getLogger(__name__)


class FormularioTallerService:
    """
    Servicio de capa de negocio responsable del procesamiento del formulario de
    ingreso de mantención (solicitud de ingreso a taller por chofer o mecánico).
    """

    def __init__(self, service: Optional[SolicitudService] = None) -> None:
        self.solicitud_service = service or solicitud_service

    async def procesar_formulario_ingreso(
        self,
        db: AsyncSession,
        dto: FormularioMantencionCreateDTO,
        creador_id: int,
        creador_nombre: Optional[str] = None,
        creador_rol: Optional[str] = None,
        foto: Optional[UploadFile] = None,
        fotos: Optional[List[UploadFile]] = None,
    ) -> SolicitudDTO:
        """
        Procesa el envío del formulario de mantención, registrando la orden de trabajo,
        evidencias fotográficas y detalles de fallas.
        """
        logger.info(
            "[FORMULARIO MANTENCION] Procesando ingreso | bus='%s' | creador_id=%s",
            dto.n_bus or dto.bus_id,
            creador_id,
        )
        return await self.solicitud_service.create_solicitud(
            db=db,
            dto=dto,
            creador_id=creador_id,
            creador_nombre=creador_nombre,
            creador_rol=creador_rol,
            foto=foto,
            fotos=fotos,
        )


formulario_taller_service = FormularioTallerService()
