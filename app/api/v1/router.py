from fastapi import APIRouter

from app.api.v1.endpoints import health
from app.modules.auth.api import router as auth_router
# from app.modules.buses.api import router as buses_router
from app.modules.mantencion.api import router as mantencion_router
from app.modules.neumaticos.api import router as neumaticos_router
from app.modules.supervision.api.router import router as supervision_router

api_router = APIRouter()

# Autenticación y Usuarios
api_router.include_router(auth_router, prefix="/auth", tags=["Autenticación"])

# Endpoints generales
api_router.include_router(health.router, tags=["Health"])

# Módulos de la Aplicación
# api_router.include_router(buses_router, prefix="/buses", tags=["Buses"])  # Deshabilitado: n_bus se maneja como string directo en 3NF
api_router.include_router(neumaticos_router, tags=["Formulario Neumático"])
api_router.include_router(mantencion_router, tags=["Formulario Mantención Taller"])
api_router.include_router(supervision_router, tags=["Supervisión y Auditoría"])
