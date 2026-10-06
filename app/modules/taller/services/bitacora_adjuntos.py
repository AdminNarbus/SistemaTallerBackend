"""Utilidades compartidas para adjuntar imágenes a eventos inmutables de bitácora."""
from typing import List, Optional

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException
from app.core.storage.storage_service import StorageService, storage_service
from app.modules.taller.dtos.bitacora_dto import ComentarioAdjuntoDTO
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_solicitud_evidencia import TallerSolicitudEvidencia


MAX_ADJUNTOS_BITACORA = 3


def normalizar_fotos(fotos: Optional[List[UploadFile]]) -> List[UploadFile]:
    archivos = [foto for foto in (fotos or []) if foto and foto.filename]
    if len(archivos) > MAX_ADJUNTOS_BITACORA:
        raise BusinessRuleException(
            f"Se permite adjuntar un máximo de {MAX_ADJUNTOS_BITACORA} imágenes por evento de bitácora."
        )
    return archivos


async def guardar_adjuntos_bitacora(
    db: AsyncSession,
    *,
    comentario: TallerSolicitudComentario,
    solicitud_id: int,
    usuario_id: int,
    fotos: Optional[List[UploadFile]],
    detalle_id: Optional[int] = None,
    storage: StorageService = storage_service,
) -> List[ComentarioAdjuntoDTO]:
    """Sube y vincula imágenes al comentario antes del commit de su evento."""
    archivos = normalizar_fotos(fotos)
    if not archivos:
        return []

    await db.flush()
    adjuntos: List[ComentarioAdjuntoDTO] = []
    evidencias: List[TallerSolicitudEvidencia] = []
    for archivo in archivos:
        resultado = await storage.upload_image(file=archivo, folder="bitacora")
        evidencia = TallerSolicitudEvidencia(
            solicitud_id=solicitud_id,
            detalle_id=detalle_id,
            usuario_id=usuario_id,
            comentario_id=comentario.id,
            url=resultado.get("path") or resultado["url"],
            original_filename=resultado.get("original_filename"),
            size_bytes=resultado.get("size_bytes"),
            content_type=resultado.get("content_type"),
        )
        db.add(evidencia)
        evidencias.append(evidencia)
        adjuntos.append(
            ComentarioAdjuntoDTO(
                id=0,
                solicitud_id=solicitud_id,
                detalle_id=detalle_id,
                usuario_id=usuario_id,
                comentario_id=comentario.id,
                url=resultado["url"],
                original_filename=resultado.get("original_filename"),
                size_bytes=resultado.get("size_bytes"),
                content_type=resultado.get("content_type"),
            )
        )

    await db.flush()
    for dto, evidencia in zip(adjuntos, evidencias):
        dto.id = evidencia.id
        dto.fecha_creacion = evidencia.fecha_creacion
    return adjuntos
