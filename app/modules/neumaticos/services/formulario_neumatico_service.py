import json
import os
import uuid
from typing import Any, Dict, Optional
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.neumaticos.repository.neumatico_repository import neumatico_repository

UPLOAD_EVIDENCIAS_DIR = os.path.join(os.getcwd(), "uploads", "evidencias")


class FormularioNeumaticoService:
    """
    Capa de Servicio para procesar formularios de neumáticos asociados a usuario_id.
    """

    async def procesar_formulario(
        self,
        usuario_id: Optional[int],
        maquina: Optional[str],
        tipo_bus: Optional[str],
        ruedas: Optional[str],
        motivo: Optional[str],
        precio: Optional[str],
        marca_fuego: Optional[str],
        evidencia: Optional[UploadFile],
        db: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        evidencia_url: Optional[str] = None
        nombre_original_evidencia = "Sin evidencia adjunta"

        # 1. Almacenamiento local de la evidencia
        if evidencia and evidencia.filename:
            nombre_original_evidencia = evidencia.filename
            extension = os.path.splitext(evidencia.filename)[1] or ".jpg"
            nombre_archivo_unico = f"{uuid.uuid4()}{extension}"
            ruta_destino = os.path.join(UPLOAD_EVIDENCIAS_DIR, nombre_archivo_unico)

            os.makedirs(UPLOAD_EVIDENCIAS_DIR, exist_ok=True)
            contenido = await evidencia.read()
            with open(ruta_destino, "wb") as f:
                f.write(contenido)

            evidencia_url = f"/uploads/evidencias/{nombre_archivo_unico}"

        # 2. Parseo de ruedas y precio
        ruedas_lista = ruedas
        if ruedas:
            try:
                ruedas_lista = json.loads(ruedas)
            except Exception:
                pass

        precio_float: Optional[float] = None
        if precio:
            try:
                precio_limpio = precio.replace(".", "").replace(",", ".")
                precio_float = float(precio_limpio)
            except Exception:
                pass

        # 3. Persistencia en BD PostgreSQL
        reporte_id: Optional[int] = None
        if db is not None:
            try:
                reporte_db = await neumatico_repository.crear_reporte(
                    db=db,
                    usuario_id=usuario_id,
                    numero_maquina=maquina,
                    tipo_bus=tipo_bus,
                    ruedas=ruedas_lista,
                    motivo=motivo,
                    precio=precio_float,
                    marca_fuego=marca_fuego,
                    evidencia_url=evidencia_url,
                )
                reporte_id = reporte_db.id
            except Exception as err:
                print(f"⚠️ Error al guardar reporte de neumáticos en BD: {err}")

        resumen_procesamiento = (
            f"Datos recibidos del formulario: "
            f"UsuarioID={usuario_id or 'N/A'}, "
            f"Máquina='{maquina or 'N/A'}', "
            f"Tipo de Bus='{tipo_bus or 'N/A'}', "
            f"Ruedas={ruedas_lista or '[]'}, "
            f"Motivo='{motivo or 'N/A'}', "
            f"Precio='{precio or 'N/A'}', "
            f"Marca de Fuego='{marca_fuego or 'N/A'}', "
            f"Evidencia Guardada='{evidencia_url or 'N/A'}'"
        )

        return {
            "status": "success",
            "message": "Formulario de neumáticos procesado y guardado exitosamente",
            "reporte_id": reporte_id,
            "resumen": resumen_procesamiento,
            "datos_recibidos": {
                "usuario_id": usuario_id,
                "maquina": maquina,
                "tipo_bus": tipo_bus,
                "ruedas": ruedas_lista,
                "motivo": motivo,
                "precio": precio,
                "marca_fuego": marca_fuego,
                "evidencia_original": nombre_original_evidencia,
                "evidencia_url": evidencia_url,
            },
        }


formulario_neumatico_service = FormularioNeumaticoService()
