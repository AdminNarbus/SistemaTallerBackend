from app.core.base import Base, TimestampMixin
from app.modules.taller.models.taller_consolidacion_archivo import TallerConsolidacionArchivo
from app.modules.taller.models.taller_correccion_visita import TallerCorreccionVisita
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.buses.models.bus import Bus
from app.modules.taller.models.categoria_falla import CategoriaFalla
from app.modules.taller.models.falla_taller import FallaTaller
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.taller.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.taller.models.taller_solicitud_estado_evento import TallerSolicitudEstadoEvento
from app.modules.taller.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.taller.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta
from app.modules.taller.models.taller_solicitud_evidencia import TallerSolicitudEvidencia
from app.modules.taller.models.taller_solicitud_estadia import TallerSolicitudEstadia
from app.modules.taller.models.taller_falla_evento import TallerFallaEvento
from app.modules.taller.models.taller_falla_evento_mecanico import TallerFallaEventoMecanico
from app.modules.formularios.models.reporte_neumatico import ReporteNeumatico
from app.modules.taller.models import historical_snapshots  # register insert hooks

__all__ = [
    "TallerCorreccionVisita",
    "TallerSolicitudEstadoEvento",
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
    "TallerSolicitudEstadia",
    "TallerFallaEvento",
    "TallerFallaEventoMecanico",
    "ReporteNeumatico",
]
