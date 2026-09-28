import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_current_user
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.taller.dtos import (
    CategoriaFallaDTO,
    FallaTallerDTO,
    PautaTallerItemDTO,
)
from app.modules.taller.services.taller_catalogo_service import taller_catalogo_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/pauta/items", response_model=List[PautaTallerItemDTO])
async def get_pauta_items(
    response: Response,
    current_user: UsuarioResponseDTO = Depends(require_current_user),
    db: AsyncSession = SessionDep,
):
    """Retorna el catálogo maestro de 11 ítems de inspección preventiva de taller."""
    response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=60"
    return await taller_catalogo_service.get_pauta_items(db)


@router.get("/categorias", response_model=List[CategoriaFallaDTO])
async def get_categorias(
    response: Response,
    db: AsyncSession = SessionDep,
):
    """Retorna las categorías de fallas activas."""
    response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=60"
    return await taller_catalogo_service.get_categorias(db)


@router.get("/fallas", response_model=List[FallaTallerDTO])
async def get_fallas(
    categoria_id: Optional[int] = Query(None, description="Filtrar por ID de categoría"),
    db: AsyncSession = SessionDep,
):
    """Retorna el catálogo maestro de fallas de taller preconcebidas."""
    return await taller_catalogo_service.get_fallas(db, categoria_id)
