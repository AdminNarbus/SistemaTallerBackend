from app.modules.taller.dtos.catalogo_dto import (
    CategoriaFallaDTO,
    FallaTallerDTO,
)
from app.modules.taller.dtos.pauta_dto import (
    PautaBatchUpdateDTO,
    PautaEstadoResumenDTO,
    PautaRespuestaCreateDTO,
    PautaRespuestaDTO,
    PautaTallerItemDTO,
)
from app.modules.taller.dtos.averias_dto import (
    AgregarFallaDTO,
    AsignacionFallaDTO,
    CheckFallaDTO,
    DetalleUpdateDTO,
    MecanicoAsignadoDTO,
    ReportarRepuestoDTO,
    ResolverFallaSupervisoraDTO,
    SolicitudDetalleCreateDTO,
    SolicitudDetalleDTO,
)
from app.modules.taller.dtos.cuadrilla_dto import (
    AgregarColaboradorDTO,
    AsignarFallasSupervisoraDTO,
    AutoasignarFallasDTO,
    LiberarTurnoDTO,
    SolicitudMecanicoDTO,
    TerminarAvanceDTO,
    TomarTrabajoDTO,
)
from app.modules.taller.dtos.bitacora_dto import (
    CambiarEstadoSolicitudDTO,
    ComentarioAddedDTO,
    ComentarioCreateDTO,
    FinalizarSolicitudDTO,
    LiberarSolicitudDTO,
    SolicitudComentarioDTO,
)
from app.modules.taller.dtos.solicitud_dto import (
    EstadiaTallerDTO,
    SolicitudCreateDTO,
    SolicitudDTO,
    SolicitudEvidenciaDTO,
    SolicitudResumenDTO,
)

__all__ = [
    # Catálogos
    "CategoriaFallaDTO",
    "FallaTallerDTO",
    # Pauta preventiva
    "PautaBatchUpdateDTO",
    "PautaEstadoResumenDTO",
    "PautaRespuestaCreateDTO",
    "PautaRespuestaDTO",
    "PautaTallerItemDTO",
    # Averías
    "AgregarFallaDTO",
    "AsignacionFallaDTO",
    "CheckFallaDTO",
    "DetalleUpdateDTO",
    "MecanicoAsignadoDTO",
    "ReportarRepuestoDTO",
    "ResolverFallaSupervisoraDTO",
    "SolicitudDetalleCreateDTO",
    "SolicitudDetalleDTO",
    # Cuadrilla
    "AgregarColaboradorDTO",
    "AsignarFallasSupervisoraDTO",
    "AutoasignarFallasDTO",
    "LiberarTurnoDTO",
    "SolicitudMecanicoDTO",
    "TerminarAvanceDTO",
    "TomarTrabajoDTO",
    # Bitácora y Cierre
    "CambiarEstadoSolicitudDTO",
    "ComentarioAddedDTO",
    "ComentarioCreateDTO",
    "FinalizarSolicitudDTO",
    "LiberarSolicitudDTO",
    "SolicitudComentarioDTO",
    # Solicitud
    "EstadiaTallerDTO",
    "SolicitudCreateDTO",
    "SolicitudDTO",
    "SolicitudEvidenciaDTO",
    "SolicitudResumenDTO",
]
