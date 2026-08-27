from app.core.base import Base
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.buses.models.bus import Bus
from app.modules.conductores.models.conductor import Conductor
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.neumaticos.models.reporte_neumatico import ReporteNeumatico

__all__ = [
    "Base",
    "Conductor",
    "Bus",
    "ReporteNeumatico",
    "TallerSolicitud",
    "Rol",
    "Usuario",
]
