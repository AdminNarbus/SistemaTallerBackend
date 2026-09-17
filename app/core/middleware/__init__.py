"""
Módulo de middlewares de seguridad e infraestructura HTTP del core.
"""
from app.core.middleware.device_restriction import DeviceRestrictionMiddleware

__all__ = ["DeviceRestrictionMiddleware"]
