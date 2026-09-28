from app.modules.formularios.api.router import router as formularios_router
from app.modules.formularios.api.neumaticos_router import router as neumaticos_router
from app.modules.formularios.api.pauta_router import router as pauta_router
from app.modules.formularios.api.taller_router import router as taller_router

__all__ = [
    "formularios_router",
    "neumaticos_router",
    "pauta_router",
    "taller_router",
]
