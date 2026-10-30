from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_supervisor_or_admin
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.formularios.dtos.pauta_dto import PautaGestionDTO, PautaGestionUpdateDTO
from app.modules.formularios.services.formulario_pauta_service import formulario_pauta_service

router = APIRouter()


@router.get("/solicitudes/{id}/pauta", response_model=PautaGestionDTO,
            summary="Consultar puntos revisados y pendientes de la pauta preventiva")
async def get_pauta_supervision(
    id: int = Path(..., ge=1),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> PautaGestionDTO:
    return await formulario_pauta_service.get_gestion(db, id)


@router.patch("/solicitudes/{id}/pauta", response_model=PautaGestionDTO,
              summary="Registrar, corregir o devolver a pendiente puntos de pauta",
              description="Actualización parcial atómica. Solo modifica los puntos enviados. "
                          "estado=null elimina la respuesta vigente y devuelve el punto a pendiente. "
                          "Cada revisión requiere mecanicos_ids de uno o más MECANICO activos; "
                          "mecanico_id se conserva para clientes de un solo revisor. "
                          "Cada cambio queda registrado en la bitácora con el usuario autenticado.")
async def actualizar_pauta_supervision(
    dto: PautaGestionUpdateDTO,
    id: int = Path(..., ge=1),
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
    db: AsyncSession = SessionDep,
) -> PautaGestionDTO:
    return await formulario_pauta_service.actualizar_gestion(db, id, dto, current_user.id)
