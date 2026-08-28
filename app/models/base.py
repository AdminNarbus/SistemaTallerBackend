from app.core.base import Base, TimestampMixin
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.conductores.models.conductor import Conductor
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.neumaticos.models.reporte_neumatico import ReporteNeumatico

__all__ = [
    "Base",
    "TimestampMixin",
    "Rol",
    "Usuario",
    "Conductor",
    "CategoriaFalla",
    "FallaTaller",
    "TallerSolicitud",
    "TallerSolicitudDetalle",
    "TallerSolicitudMecanico",
    "TallerSolicitudComentario",
    "ReporteNeumatico",
]
