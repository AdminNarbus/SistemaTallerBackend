from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.buses.models.bus import Bus
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
        bus_id: Optional[int] = None,
    ) -> ReporteNeumatico:
        ahora = datetime.now(timezone.utc)

        # Resolver bus_id a partir de n_bus / numero_maquina si no viene provisto
        if not bus_id and numero_maquina:
            clean_nb = str(numero_maquina).strip()
            bus_res = await db.execute(select(Bus.id).where(Bus.n_bus == clean_nb))
            bus_id = bus_res.scalar_one_or_none()

        reporte = ReporteNeumatico(
            usuario_id=usuario_id,
            bus_id=bus_id,
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

