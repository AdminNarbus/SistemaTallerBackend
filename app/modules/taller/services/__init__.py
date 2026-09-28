from app.modules.taller.services.taller_service import (
    TallerService,
    taller_service,
)
from app.modules.taller.services.taller_catalogo_service import (
    TallerCatalogoService,
    taller_catalogo_service,
)
from app.modules.taller.services.pauta_service import (
    PautaService,
    pauta_service,
)
from app.modules.taller.services.solicitud_service import (
    SolicitudService,
    solicitud_service,
)
from app.modules.taller.services.cuadrilla_service import (
    CuadrillaService,
    cuadrilla_service,
)
from app.modules.taller.services.averias_service import (
    AveriasService,
    averias_service,
)
from app.modules.taller.services.cierre_service import (
    CierreService,
    cierre_service,
)
from app.modules.taller.services.mappers import (
    mapear_a_solicitud_dto,
    dict_to_solicitud_dto,
    dict_to_solicitud_resumen_dto,
    orm_to_solicitud_dto,
)

__all__ = [
    "TallerService",
    "taller_service",
    "TallerCatalogoService",
    "taller_catalogo_service",
    "PautaService",
    "pauta_service",
    "SolicitudService",
    "solicitud_service",
    "CuadrillaService",
    "cuadrilla_service",
    "AveriasService",
    "averias_service",
    "CierreService",
    "cierre_service",
    "mapear_a_solicitud_dto",
    "dict_to_solicitud_dto",
    "dict_to_solicitud_resumen_dto",
    "orm_to_solicitud_dto",
]
