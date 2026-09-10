from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_mecanico import TallerSolicitudMecanico
from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.mantencion.models.taller_asignacion_falla import TallerAsignacionFalla
from app.modules.mantencion.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta
from app.modules.mantencion.models.taller_solicitud_evidencia import TallerSolicitudEvidencia

__all__ = [
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
]

