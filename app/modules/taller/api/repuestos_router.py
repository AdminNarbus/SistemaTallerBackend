"""Endpoints del catálogo y de los repuestos utilizados."""
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_mecanico_or_supervisor_or_admin, require_supervisor_or_admin
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.taller.dtos.repuesto_dto import AnularRepuestoUtilizadoDTO, RegistrarRepuestoUtilizadoDTO, RepuestoActualizarDTO, RepuestoCrearDTO, RepuestoDTO, RepuestoUtilizadoDTO
from app.modules.taller.services.repuesto_service import repuesto_service

IdPositivo = Annotated[int, Path(gt=0)]

router = APIRouter()


@router.get("/repuestos", response_model=list[RepuestoDTO])
async def listar_repuestos(response: Response, q: str | None = Query(None, max_length=150), incluir_inactivos: bool = False, skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), actor: UsuarioResponseDTO = Depends(require_mecanico_or_supervisor_or_admin), db: AsyncSession = SessionDep):
    filas, total = await repuesto_service.listar_catalogo(db, actor, q, incluir_inactivos, skip, limit)
    response.headers["X-Total-Count"] = str(total)
    return filas


@router.post("/repuestos", response_model=RepuestoDTO, status_code=201)
async def crear_repuesto(dto: RepuestoCrearDTO, actor: UsuarioResponseDTO = Depends(require_supervisor_or_admin), db: AsyncSession = SessionDep):
    return await repuesto_service.guardar_catalogo(db, dto)


@router.patch("/repuestos/{repuesto_id}", response_model=RepuestoDTO)
async def editar_repuesto(repuesto_id: IdPositivo, dto: RepuestoActualizarDTO, actor: UsuarioResponseDTO = Depends(require_supervisor_or_admin), db: AsyncSession = SessionDep):
    return await repuesto_service.guardar_catalogo(db, dto, repuesto_id)


@router.get("/{id}/detalles/{detalle_id}/repuestos-utilizados", response_model=list[RepuestoUtilizadoDTO])
async def listar_repuestos_falla(id: IdPositivo, detalle_id: IdPositivo, response: Response, incluir_anulados: bool = False, skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), actor: UsuarioResponseDTO = Depends(require_mecanico_or_supervisor_or_admin), db: AsyncSession = SessionDep):
    filas, total = await repuesto_service.listar_usos(db, id, detalle_id, incluir_anulados, skip, limit)
    response.headers["X-Total-Count"] = str(total)
    return filas


@router.get("/{id}/repuestos-utilizados", response_model=list[RepuestoUtilizadoDTO])
async def listar_repuestos_ot(id: IdPositivo, response: Response, incluir_anulados: bool = False, skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), actor: UsuarioResponseDTO = Depends(require_mecanico_or_supervisor_or_admin), db: AsyncSession = SessionDep):
    filas, total = await repuesto_service.listar_usos(db, id, None, incluir_anulados, skip, limit)
    response.headers["X-Total-Count"] = str(total)
    return filas


@router.post("/{id}/detalles/{detalle_id}/repuestos-utilizados", response_model=RepuestoUtilizadoDTO, status_code=201)
async def registrar_repuesto(id: IdPositivo, detalle_id: IdPositivo, dto: RegistrarRepuestoUtilizadoDTO, response: Response, actor: UsuarioResponseDTO = Depends(require_mecanico_or_supervisor_or_admin), db: AsyncSession = SessionDep):
    resultado, creado = await repuesto_service.registrar(db, id, detalle_id, dto, actor)
    response.status_code = 201 if creado else 200
    return resultado


@router.patch("/{id}/detalles/{detalle_id}/repuestos-utilizados/{registro_id}/anulacion", response_model=RepuestoUtilizadoDTO)
async def anular_repuesto(id: IdPositivo, detalle_id: IdPositivo, registro_id: IdPositivo, dto: AnularRepuestoUtilizadoDTO, actor: UsuarioResponseDTO = Depends(require_mecanico_or_supervisor_or_admin), db: AsyncSession = SessionDep):
    return await repuesto_service.anular(db, id, detalle_id, registro_id, dto, actor)
