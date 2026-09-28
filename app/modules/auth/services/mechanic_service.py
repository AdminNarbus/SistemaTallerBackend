import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.constants import DEFAULT_PAGE_SKIP, DEFAULT_PAGE_LIMIT
from app.modules.auth.dtos import UsuarioResponseDTO
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.repository.user_repository import user_repository

logger = logging.getLogger(__name__)


class MechanicService:
    """
    Capa de servicio de negocio especializada en la consulta y resolución de mecánicos
    para cuadrillas, asignaciones atómicas y autocompletado en el frontend.
    """

    async def buscar_mecanicos(
        self,
        db: AsyncSession,
        q: Optional[str] = None,
        exclude_id: Optional[int] = None,
        skip: int = DEFAULT_PAGE_SKIP,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> List[UsuarioResponseDTO]:
        """Busca mecánicos activos con paginación (default: 20) y filtros opcionales."""
        mecanicos = await user_repository.buscar_mecanicos(
            db, q=q, exclude_id=exclude_id, skip=skip, limit=limit
        )
        return [UsuarioResponseDTO.model_validate(m) for m in mecanicos]

    async def contar_mecanicos(
        self,
        db: AsyncSession,
        q: Optional[str] = None,
        exclude_id: Optional[int] = None,
    ) -> int:
        """Retorna el conteo total de mecánicos activos bajo los filtros de búsqueda."""
        return await user_repository.count_mecanicos(
            db, q=q, exclude_id=exclude_id
        )

    async def resolver_mecanicos_por_nombres(
        self, db: AsyncSession, nombres: List[str]
    ) -> List[Usuario]:
        """Resuelve usuarios mecánicos en base a una lista de nombres de usuario o nombres completos."""
        return await user_repository.get_mecanicos_by_nombres_o_usernames(db, nombres=nombres)


mechanic_service = MechanicService()

__all__ = ["MechanicService", "mechanic_service"]
