from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bus import Bus
from app.models.reporte_neumatico import ReporteNeumatico


async def crear_reporte_neumatico(
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
    """
    Crea e inserta un reporte de neumáticos vinculado exclusivamente a usuario_id y bus_id.
    """
    bus_id: Optional[int] = None
    if numero_maquina and str(numero_maquina).strip():
        res_b = await db.execute(
            select(Bus.id).where(Bus.n_bus == str(numero_maquina).strip())
        )
        bus_id = res_b.scalar_one_or_none()

    ahora = datetime.now(timezone.utc)

    reporte = ReporteNeumatico(
        usuario_id=usuario_id,
        bus_id=bus_id,
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
