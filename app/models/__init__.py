from app.core.base import Base, TimestampMixin
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.buses.models.bus import Bus
from app.modules.taller.models.categoria_falla import CategoriaFalla
from app.modules.taller.models.falla_taller import FallaTaller
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta
from app.modules.taller.models.taller_solicitud_evidencia import TallerSolicitudEvidencia
from app.modules.formularios.models.reporte_neumatico import ReporteNeumatico

__all__ = [
    "Base",
    "TimestampMixin",
    "Rol",
    "Usuario",
    "Bus",
    "CategoriaFalla",
    "FallaTaller",
    "TallerSolicitud",
    "TallerSolicitudDetalle",
    "TallerSolicitudMecanico",
    "TallerSolicitudComentario",
    "TallerAsignacionFalla",
    "PautaTallerItem",
    "TallerSolicitudPauta",
    "TallerSolicitudEvidencia",
    "ReporteNeumatico",
]
