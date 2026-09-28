from fastapi import APIRouter

from app.api.v1.endpoints import health
from app.modules.auth.api import router as auth_router
from app.modules.buses.api.router import router as buses_router
from app.modules.formularios.api import formularios_router
from app.modules.taller.api import router as taller_router
from app.modules.supervision.api.router import router as supervision_router

api_router = APIRouter()

# Autenticación y Usuarios
api_router.include_router(auth_router, prefix="/auth", tags=["Autenticación"])

# Endpoints generales
api_router.include_router(health.router, tags=["Health"])

# Módulos de la Aplicación
api_router.include_router(buses_router, prefix="/buses", tags=["Buses"])
api_router.include_router(formularios_router, prefix="/formularios", tags=["Formularios Unificados"])
api_router.include_router(taller_router, tags=["Operativa de Taller"])
api_router.include_router(supervision_router, tags=["Supervisión y Auditoría"])


