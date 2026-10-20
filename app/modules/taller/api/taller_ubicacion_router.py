from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_mecanico_or_supervisor_or_admin, require_supervisor_or_admin
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.taller.dtos.taller_ubicacion_dto import CiudadCrearDTO, CiudadDTO, CorregirUbicacionDTO, TallerActualizarDTO, TallerCrearDTO, TallerDTO, UbicacionEventoDTO
from app.modules.taller.services.taller_ubicacion_catalogo_service import taller_ubicacion_catalogo_service
from app.modules.taller.services.resultado_falla_service import resultado_falla_service

router = APIRouter()


@router.get("/ciudades", response_model=list[CiudadDTO])
async def ciudades(_actor: UsuarioResponseDTO = Depends(require_mecanico_or_supervisor_or_admin), db: AsyncSession = SessionDep):
    return await taller_ubicacion_catalogo_service.listar_ciudades(db)


@router.post("/ciudades", response_model=CiudadDTO, status_code=201)
async def crear_ciudad(dto: CiudadCrearDTO, _actor: UsuarioResponseDTO = Depends(require_supervisor_or_admin), db: AsyncSession = SessionDep):
    return await taller_ubicacion_catalogo_service.crear_ciudad(db, dto)


@router.get("/talleres", response_model=list[TallerDTO])
async def talleres(
    response: Response,
    ciudad_id: Optional[int] = Query(None, gt=0),
    tipo: Optional[str] = Query(None, pattern="^(INTERNO|EXTERNO)$"),
    is_activo: Optional[bool] = None,
    q: Optional[str] = Query(None, max_length=200),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    _actor: UsuarioResponseDTO = Depends(require_mecanico_or_supervisor_or_admin),
    db: AsyncSession = SessionDep,
):
    rows, total = await taller_ubicacion_catalogo_service.listar_talleres(db, dict(ciudad_id=ciudad_id, tipo=tipo, is_activo=is_activo, q=q, skip=skip, limit=limit))
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.post("/talleres", response_model=TallerDTO, status_code=201)
async def crear_taller(dto: TallerCrearDTO, _actor: UsuarioResponseDTO = Depends(require_supervisor_or_admin), db: AsyncSession = SessionDep):
    return await taller_ubicacion_catalogo_service.crear_taller(db, dto)


@router.patch("/talleres/{taller_id}", response_model=TallerDTO)
async def actualizar_taller(taller_id: int, dto: TallerActualizarDTO, _actor: UsuarioResponseDTO = Depends(require_supervisor_or_admin), db: AsyncSession = SessionDep):
    return await taller_ubicacion_catalogo_service.actualizar_taller(db, taller_id, dto)


@router.post("/{id}/detalles/{detalle_id}/eventos/{evento_id}/ubicacion", response_model=UbicacionEventoDTO, status_code=201)
async def corregir_ubicacion(
    id: int, detalle_id: int, evento_id: int, dto: CorregirUbicacionDTO,
    actor: UsuarioResponseDTO = Depends(require_supervisor_or_admin), db: AsyncSession = SessionDep,
):
    return await resultado_falla_service.corregir_ubicacion(
        db, id, detalle_id, evento_id, actor.id, actor.nombre_completo, actor.rol, dto,
    )
