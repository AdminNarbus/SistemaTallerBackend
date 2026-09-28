from fastapi import APIRouter

from app.modules.taller.api.catalogo_router import router as catalogo_router
from app.modules.taller.api.solicitud_router import router as solicitud_router
from app.modules.taller.api.pauta_router import router as pauta_router
from app.modules.taller.api.cuadrilla_router import router as cuadrilla_router
from app.modules.taller.api.averias_router import router as averias_router
from app.modules.taller.api.cierre_router import router as cierre_router

router = APIRouter(prefix="/taller", tags=["Taller"])

# Inclusión de sub-routers organizados por responsabilidad única (SRP)
router.include_router(catalogo_router)
router.include_router(solicitud_router)
router.include_router(pauta_router)
router.include_router(cuadrilla_router)
router.include_router(averias_router)
router.include_router(cierre_router)

__all__ = [
    "router",
    "catalogo_router",
    "solicitud_router",
    "pauta_router",
    "cuadrilla_router",
    "averias_router",
    "cierre_router",
]
