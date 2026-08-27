import base64
import os
import uuid
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.mantencion.dtos.taller_solicitud_dto import SolicitudMantencionCreateDTO
from app.modules.mantencion.repository.taller_solicitud_repository import (
    taller_solicitud_repository,
)

UPLOAD_MANTENCIONES_DIR = os.path.join(os.getcwd(), "uploads", "mantenciones")


class FormularioMantencionService:
    """
    Capa de Servicio para procesar solicitudes de Mantención Taller vinculadas a usuario_id.
    """

    async def procesar_solicitud(
        self,
        payload: SolicitudMantencionCreateDTO,
        db: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        foto_url: Optional[str] = None

        if payload.foto_base64 and payload.foto_base64.strip():
            try:
                base64_str = payload.foto_base64.strip()
                extension = ".jpg"

                if "," in base64_str:
                    header, base64_str = base64_str.split(",", 1)
                    if "png" in header.lower():
                        extension = ".png"
                    elif "webp" in header.lower():
                        extension = ".webp"

                img_bytes = base64.b64decode(base64_str)
                nombre_archivo = f"{uuid.uuid4()}{extension}"
                os.makedirs(UPLOAD_MANTENCIONES_DIR, exist_ok=True)
                ruta_archivo = os.path.join(UPLOAD_MANTENCIONES_DIR, nombre_archivo)

                with open(ruta_archivo, "wb") as f:
                    f.write(img_bytes)

                foto_url = f"/uploads/mantenciones/{nombre_archivo}"
            except Exception as e:
                print(f"⚠️ Error procesando foto_base64 en solicitud taller: {e}")

        solicitud_id: Optional[int] = None
        if db is not None:
            solicitud_db = await taller_solicitud_repository.crear_solicitud(
                db=db,
                usuario_id=payload.usuario_id,
                id_bus=payload.id_bus,
                n_bus=payload.n_bus,
                descripcion=payload.descripcion,
                items=payload.items,
                foto_url=foto_url,
                estado=payload.estado or "PENDIENTE",
            )
            solicitud_id = solicitud_db.id

        return {
            "status": "success",
            "message": "Solicitud de mantención de taller guardada exitosamente en taller_solicitudes",
            "solicitud_id": solicitud_id,
            "foto_url": foto_url,
            "datos": {
                "usuario_id": payload.usuario_id,
                "id_bus": payload.id_bus,
                "n_bus": payload.n_bus,
                "descripcion": payload.descripcion,
                "items": payload.items,
                "estado": payload.estado or "PENDIENTE",
            },
        }


formulario_mantencion_service = FormularioMantencionService()
