from fastapi import APIRouter

from app.api.v1.endpoints import health, items, buses
from app.api.v1.endpoints.formularios import neumaticos, mantencion_taller

api_router = APIRouter()

# Endpoints generales
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(items.router, prefix="/items", tags=["Items"])
api_router.include_router(buses.router, prefix="/buses", tags=["Buses"])


# Router de Formularios del Taller
api_router.include_router(
    neumaticos.router, tags=["Formulario Neumático"]
)
api_router.include_router(
    mantencion_taller.router, tags=["Formulario Mantención Taller"]
)
