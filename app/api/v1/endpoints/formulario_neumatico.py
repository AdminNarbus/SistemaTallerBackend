"""
Módulo legado: Reexporta el router desde app.api.v1.endpoints.formularios.neumaticos
para mantener compatibilidad total.
"""
from app.api.v1.endpoints.formularios.neumaticos import router

__all__ = ["router"]
