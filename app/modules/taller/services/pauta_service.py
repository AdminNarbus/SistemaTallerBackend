"""
Fachada retrocompatible para el servicio de pauta preventiva.
Delega al nuevo módulo consolidado app.modules.formularios.services.formulario_pauta_service.
"""
from app.modules.formularios.services.formulario_pauta_service import (
    FormularioPautaService,
    formulario_pauta_service,
    PautaService,
    pauta_service,
)

__all__ = [
    "FormularioPautaService",
    "formulario_pauta_service",
    "PautaService",
    "pauta_service",
]
