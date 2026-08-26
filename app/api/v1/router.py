from fastapi import APIRouter

from app.api.v1.endpoints import auth, buses, health, items
from app.api.v1.endpoints.formularios import mantencion_taller, neumaticos

api_router = APIRouter()

# Autenticación y Usuarios
api_router.include_router(auth.router, prefix="/auth", tags=["Autenticación"])

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
