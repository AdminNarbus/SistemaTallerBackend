import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.taller.dtos import (
    CategoriaFallaDTO,
    FallaTallerDTO,
    PautaTallerItemDTO,
)
from app.modules.taller.repository.taller_repository import (
    TallerRepository,
    taller_repository,
)

logger = logging.getLogger(__name__)


class TallerCatalogoService:
    """
    Servicio de capa de negocio responsable exclusivamente de los catálogos maestros
    de mantención: categorías de fallas, catálogo de averías preconcebidas y
    los 11 ítems estándar de la pauta preventiva de maestranza.
    """

    def __init__(self, repository: Optional[TallerRepository] = None) -> None:
        self.repo = repository or taller_repository

    async def get_categorias(self, db: AsyncSession) -> List[CategoriaFallaDTO]:
        """Retorna las categorías de fallas activas con sus respectivas averías."""
        cats = await self.repo.get_categorias_con_fallas(db)
        return [CategoriaFallaDTO(**c) for c in cats]

    async def get_fallas(
        self, db: AsyncSession, categoria_id: Optional[int] = None
    ) -> List[FallaTallerDTO]:
        """Retorna el catálogo maestro de fallas de taller preconcebidas."""
        fallas = await self.repo.get_fallas(db, categoria_id)
        res = []
        for f in fallas:
            cat_dto = None
            if f.categoria:
                cat_dto = CategoriaFallaDTO(
                    id=f.categoria.id,
                    nombre=f.categoria.nombre,
                    is_active=f.categoria.is_active,
                    falla_id=f.id,
                    falla_nombre=f.nombre,
                )
            res.append(
                FallaTallerDTO(
                    id=f.id,
                    categoria_id=f.categoria_id,
                    nombre=f.nombre,
                    is_active=f.is_active,
                    categoria=cat_dto,
                )
            )
        return res

    async def get_pauta_items(self, db: AsyncSession) -> List[PautaTallerItemDTO]:
        """Retorna el catálogo maestro de ítems de inspección preventiva de taller."""
        items = await self.repo.get_pauta_items(db)
        return [PautaTallerItemDTO.model_validate(it) for it in items]


taller_catalogo_service = TallerCatalogoService()
