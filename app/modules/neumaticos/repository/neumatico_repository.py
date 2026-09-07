import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.buses.models.bus import Bus
from app.modules.neumaticos.models.reporte_neumatico import ReporteNeumatico

logger = logging.getLogger(__name__)


class NeumaticoRepository:
    """
    Repositorio de Persistencia Pura (SQL) para reportes de neumáticos.
    Responsabilidad exclusiva: Ejecución de consultas CRUD atómicas sobre la base de datos.
    No gestiona lógica de negocio ni realiza commits de transacciones.
    """

    async def add(self, db: AsyncSession, reporte: ReporteNeumatico) -> ReporteNeumatico:
        """
        Agrega atómicamente un nuevo reporte de neumático a la sesión y realiza flush.
        El commit final es responsabilidad exclusiva de la capa de Servicio.
        """
        db.add(reporte)
        await db.flush()
        return reporte

    async def get_by_id(self, db: AsyncSession, reporte_id: int) -> Optional[ReporteNeumatico]:
        """Obtiene un reporte de neumático por su clave primaria."""
        stmt = select(ReporteNeumatico).where(ReporteNeumatico.id == reporte_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_bus_by_numero(self, db: AsyncSession, numero_maquina: str) -> Optional[Bus]:
        """Consulta atómica para resolver un Bus a partir de su número de máquina / n_bus."""
        if not numero_maquina:
            return None
        clean_nb = str(numero_maquina).strip()
        stmt = select(Bus).where(Bus.n_bus == clean_nb)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_reportes(
        self, db: AsyncSession, limit: int = 50, offset: int = 0
    ) -> Sequence[ReporteNeumatico]:
        """Obtiene el listado paginado de reportes ordenados cronológicamente descendente."""
        stmt = (
            select(ReporteNeumatico)
            .order_by(ReporteNeumatico.fecha_subida.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    async def count(self, db: AsyncSession) -> int:
        """Retorna el conteo total de reportes de neumáticos registrados."""
        stmt = select(func.count(ReporteNeumatico.id))
        result = await db.execute(stmt)
        return result.scalar_one() or 0

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
        """
        Método de conveniencia atómico (crea y añade la entidad con flush, sin commit).
        Mantenido para compatibilidad con llamadas existentes.
        """
        if not bus_id and numero_maquina:
            bus = await self.get_bus_by_numero(db, numero_maquina)
            if bus:
                bus_id = bus.id

        ahora = datetime.now(timezone.utc)
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
        return await self.add(db, reporte)


neumatico_repository = NeumaticoRepository()
