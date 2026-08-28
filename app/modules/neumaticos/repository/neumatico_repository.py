from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.neumaticos.models.reporte_neumatico import ReporteNeumatico


class NeumaticoRepository:
    """Repositorio para guardar e interactuar con reportes de neumáticos en la BD."""

    async def crear_reporte(
        self,
        db: AsyncSession,
        usuario_id: Optional[int],
        numero_maquina: Optional[str],
        tipo_bus: Optional[str],
        ruedas: Optional[Any],
        motivo: Optional[str],
        precio: Optional[float],
        marca_fuego: Optional[str],
        evidencia_url: Optional[str],
    ) -> ReporteNeumatico:
        ahora = datetime.now(timezone.utc)

        reporte = ReporteNeumatico(
            usuario_id=usuario_id,
            n_bus=numero_maquina,
            tipo_bus=tipo_bus,
            ruedas=ruedas,
            motivo=motivo,
            precio=precio,
            marca_fuego=marca_fuego,
            evidencia_url=evidencia_url,
            fecha_subida=ahora,
        )

        db.add(reporte)
        await db.commit()
        await db.refresh(reporte)
        return reporte


neumatico_repository = NeumaticoRepository()
