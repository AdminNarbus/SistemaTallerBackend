import logging
from fastapi import APIRouter

from app.modules.formularios.api.neumaticos_router import router as neumaticos_router
from app.modules.formularios.api.pauta_router import router as pauta_router
from app.modules.formularios.api.taller_router import router as taller_router

logger = logging.getLogger(__name__)

router = APIRouter()

# Incorporar sub-routers del dominio de Formularios
router.include_router(neumaticos_router, tags=["Formulario Neumático"])
router.include_router(pauta_router, tags=["Formulario Pauta Preventiva"])
router.include_router(taller_router, tags=["Formulario Ingreso Mantención"])
