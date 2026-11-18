"""API del módulo preventivo, restringida a Supervisor y Admin."""

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_supervisor_or_admin
from app.core.exceptions import BusinessRuleException
from app.modules.auth.dtos.usuario_dto import UsuarioResponseDTO
from app.modules.control_mantenciones.dtos.contracts import (
    Borrador,
    Comentario,
    Decision,
    Filtros,
    IntervaloEditar,
    LecturaCrear,
    LecturaEditar,
    MantencionCrear,
    MantencionEditar,
    Operacion,
    Pagina,
    Panel,
    Recurso,
    ResultadoCarga,
    Revision,
    Version,
    VistaPrevia,
)
from app.modules.control_mantenciones.models.entities import (
    ControlEvento,
    ControlKilometraje,
    ControlMantencion,
)
from app.modules.control_mantenciones.services.exports import exportar
from app.modules.control_mantenciones.services.imports import (
    MAX_BYTES,
    ImportService,
    leer_excel,
)
from app.modules.control_mantenciones.services.operations import OperationsService
from app.modules.control_mantenciones.services.queries import QueryService

router = APIRouter(dependencies=[Depends(require_supervisor_or_admin)])
Actor = Annotated[UsuarioResponseDTO, Depends(require_supervisor_or_admin)]
Filtro = Annotated[Filtros, Query()]


@router.get("/panel", response_model=Panel)
async def panel(filtros: Filtro, db: AsyncSession = SessionDep) -> dict:
    return await QueryService(db).panel(filtros)


@router.get("/buses/{bus_id}", response_model=Recurso)
async def ficha(bus_id: int, db: AsyncSession = SessionDep) -> dict:
    return {"datos": await QueryService(db).ficha(bus_id)}


@router.patch("/buses/{bus_id}/intervalo", response_model=Recurso)
async def intervalo(
    bus_id: int, datos: IntervaloEditar, actor: Actor, db: AsyncSession = SessionDep
) -> dict:
    return {"datos": await OperationsService(db, actor.id).intervalo(bus_id, datos)}


@router.get("/buses/{bus_id}/grafico", response_model=Recurso)
async def grafico(bus_id: int, db: AsyncSession = SessionDep) -> dict:
    return {"datos": await QueryService(db).grafico(bus_id)}


@router.get("/buses/{bus_id}/proyeccion", response_model=Recurso)
async def proyeccion(bus_id: int, db: AsyncSession = SessionDep) -> dict:
    return {"datos": await QueryService(db).proyeccion(bus_id)}


@router.get("/historial", response_model=Pagina)
async def historial(filtros: Filtro, db: AsyncSession = SessionDep) -> dict:
    return await QueryService(db).historial(filtros)


@router.get("/mantenciones", response_model=Pagina)
async def mantenciones(filtros: Filtro, db: AsyncSession = SessionDep) -> dict:
    return await QueryService(db).historial(
        filtros.model_copy(update={"tipo": "mantencion"})
    )


@router.post("/mantenciones", response_model=Recurso, status_code=201)
async def crear_mantencion(
    datos: MantencionCrear, actor: Actor, db: AsyncSession = SessionDep
) -> dict:
    return {"datos": await OperationsService(db, actor.id).crear_mantencion(datos)}


@router.get("/mantenciones/{identificador}", response_model=Recurso)
async def mantencion(identificador: int, db: AsyncSession = SessionDep) -> dict:
    return {"datos": await QueryService(db).detalle(ControlMantencion, identificador)}


@router.patch("/mantenciones/{identificador}", response_model=Recurso)
async def editar_mantencion(
    identificador: int,
    datos: MantencionEditar,
    actor: Actor,
    db: AsyncSession = SessionDep,
) -> dict:
    return {
        "datos": await OperationsService(db, actor.id).editar_mantencion(
            identificador, datos
        )
    }


@router.delete("/mantenciones/{identificador}", response_model=Operacion)
async def eliminar_mantencion(
    identificador: int, datos: Version, actor: Actor, db: AsyncSession = SessionDep
) -> dict:
    await OperationsService(db, actor.id).eliminar_mantencion(
        identificador, datos.version
    )
    return {
        "mensaje": "Mantención eliminada; su eliminación quedó en el historial de cambios."
    }


@router.post(
    "/mantenciones/{identificador}/comentarios", response_model=Recurso, status_code=201
)
async def comentar(
    identificador: int, datos: Comentario, actor: Actor, db: AsyncSession = SessionDep
) -> dict:
    return {
        "datos": await OperationsService(db, actor.id).comentar(identificador, datos)
    }


@router.get("/kilometrajes", response_model=Pagina)
async def kilometrajes(filtros: Filtro, db: AsyncSession = SessionDep) -> dict:
    return await QueryService(db).historial(
        filtros.model_copy(update={"tipo": "kilometraje"})
    )


@router.post("/kilometrajes", response_model=Recurso, status_code=201)
async def crear_lectura(
    datos: LecturaCrear, actor: Actor, db: AsyncSession = SessionDep
) -> dict:
    return {"datos": await OperationsService(db, actor.id).crear_lectura(datos)}


@router.get("/kilometrajes/{identificador}", response_model=Recurso)
async def lectura(identificador: int, db: AsyncSession = SessionDep) -> dict:
    return {"datos": await QueryService(db).detalle(ControlKilometraje, identificador)}


@router.patch("/kilometrajes/{identificador}", response_model=Recurso)
async def editar_lectura(
    identificador: int,
    datos: LecturaEditar,
    actor: Actor,
    db: AsyncSession = SessionDep,
) -> dict:
    return {
        "datos": await OperationsService(db, actor.id).editar_lectura(
            identificador, datos
        )
    }


@router.delete("/kilometrajes/{identificador}", response_model=Operacion)
async def eliminar_lectura(
    identificador: int, datos: Version, actor: Actor, db: AsyncSession = SessionDep
) -> dict:
    await OperationsService(db, actor.id).eliminar_lectura(identificador, datos.version)
    return {"mensaje": "Lectura eliminada; su eliminación quedó en el historial de cambios."}


@router.post("/kilometrajes/{identificador}/decisiones", response_model=Recurso)
async def decision(
    identificador: int, datos: Decision, actor: Actor, db: AsyncSession = SessionDep
) -> dict:
    return {
        "datos": await OperationsService(db, actor.id).decidir(identificador, datos)
    }


@router.post("/importaciones/previsualizacion", response_model=VistaPrevia)
async def previsualizar(
    actor: Actor, files: list[UploadFile] = File(...), db: AsyncSession = SessionDep
) -> dict:
    if not 1 <= len(files) <= 10:
        raise BusinessRuleException("Seleccione entre uno y diez archivos Excel.")
    revisiones = []
    for archivo in files:
        contenido = await archivo.read(MAX_BYTES + 1)
        borrador = await asyncio.to_thread(
            leer_excel, archivo.filename or "", contenido
        )
        revisiones.append(await ImportService(db, actor.id).revisar(borrador))
        await archivo.close()
    return {"revisiones": revisiones}


@router.post("/importaciones/validaciones", response_model=Revision)
async def validar(
    borrador: Borrador, actor: Actor, db: AsyncSession = SessionDep
) -> dict:
    return await ImportService(db, actor.id).revisar(borrador)


@router.post("/importaciones", response_model=ResultadoCarga, status_code=201)
async def confirmar(
    borrador: Borrador, actor: Actor, db: AsyncSession = SessionDep
) -> dict:
    return await ImportService(db, actor.id).confirmar(borrador)


@router.get("/importaciones", response_model=Pagina)
async def cargas(filtros: Filtro, db: AsyncSession = SessionDep) -> dict:
    return await QueryService(db).eventos(filtros, "carga_confirmada")


@router.get("/importaciones/{identificador}", response_model=Recurso)
async def carga(identificador: int, db: AsyncSession = SessionDep) -> dict:
    return {"datos": await QueryService(db).detalle_carga(identificador)}


@router.get("/importaciones/{identificador}/filas", response_model=Pagina)
async def filas_carga(
    identificador: int, filtros: Filtro, db: AsyncSession = SessionDep
) -> dict:
    return await QueryService(db).filas_carga(identificador, filtros)


@router.delete("/importaciones/{identificador}", response_model=Operacion)
async def eliminar_carga(
    identificador: int,
    actor: Actor,
    confirmar: bool = Query(False),
    db: AsyncSession = SessionDep,
) -> dict:
    if not confirmar:
        raise BusinessRuleException(
            "Confirme la eliminación de la carga y todos sus registros asociados."
        )
    await ImportService(db, actor.id).eliminar_carga(identificador)
    return {"mensaje": "Carga, kilometrajes y trazabilidad asociada eliminados."}


@router.get("/eventos", response_model=Pagina)
async def eventos(filtros: Filtro, db: AsyncSession = SessionDep) -> dict:
    return await QueryService(db).eventos(filtros)


@router.get(
    "/exportaciones",
    response_model=None,
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {}
            },
            "description": "Reporte Excel",
        }
    },
)
async def reporte(filtros: Filtro, db: AsyncSession = SessionDep) -> Response:
    contenido = await exportar(db, filtros, filtros.area, filtros.estados_panel)
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="control-mantenciones.xlsx"'
        },
    )
