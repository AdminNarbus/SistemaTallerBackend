"""Integración funcional y concurrencia sobre PostgreSQL temporal con Alembic."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from sqlalchemy import func, select
from openpyxl import load_workbook

from app.core.exceptions import BusinessRuleException, ConflictException
from app.modules.control_mantenciones.dtos.contracts import (
    Borrador,
    Comentario,
    Decision,
    FilaBorrador,
    Filtros,
    IntervaloEditar,
    LecturaCrear,
    LecturaEditar,
    MantencionCrear,
    MantencionEditar,
)
from app.modules.control_mantenciones.models.entities import (
    ControlEvento as Evento,
    ControlKilometraje as Km,
    ControlMantencion as Mant,
)
from app.modules.control_mantenciones.services.domain import hoy
from app.modules.control_mantenciones.services.exports import exportar
from app.modules.control_mantenciones.services.imports import ImportService
from app.modules.control_mantenciones.services.operations import OperationsService
from app.modules.control_mantenciones.services.queries import QueryService

ACTOR = 900001


def borrador(km="150000", fecha=None, bus="354"):
    return Borrador(
        nombre_archivo="semana.xlsx",
        filas=[
            FilaBorrador(
                fila=2, numero_bus=bus, fecha=fecha or hoy().isoformat(), kilometraje=km
            )
        ],
    )


async def test_flujo_confirmacion_borrado_y_panel(sesiones):
    async with sesiones() as db:
        ops = OperationsService(db, ACTOR)
        query = QueryService(db)
        servicio = ImportService(db, ACTOR)
        mant = await ops.crear_mantencion(
            MantencionCrear(
                bus_id=ACTOR, fecha=hoy() - timedelta(days=20), kilometraje=100000
            )
        )
        antes = await db.scalar(select(func.count()).select_from(Evento))
        carga = borrador("120000")
        revision = await servicio.revisar(carga)
        assert revision.resultados[0].estado == "aceptado"
        assert await db.scalar(select(func.count()).select_from(Evento)) == antes
        assert await db.scalar(select(func.count()).select_from(Km)) == 0
        confirmado = await servicio.confirmar(carga)
        assert (await servicio.confirmar(carga))["carga_id"] == confirmado["carga_id"]
        ficha = await query.ficha(ACTOR)
        assert ficha["kilometraje_actual"] == 120000 and ficha["restantes"] == 20000
        panel = await query.panel(Filtros())
        assert panel["total"] == 2
        historial = await query.historial(Filtros(bus_id=ACTOR))
        assert historial["total"] == 2
        contenido = await exportar(db, Filtros(bus_id=ACTOR), "historial")
        libro = load_workbook(BytesIO(contenido))
        assert libro.active.max_row == 3
        grafico = await query.grafico(ACTOR)
        assert grafico["paso_kilometraje"] == 25000
        await servicio.eliminar_carga(confirmado["carga_id"])
        assert (await query.ficha(ACTOR))["kilometraje_actual"] == 100000
        assert await db.scalar(select(func.count()).select_from(Km)) == 0
        assert not (await query.eventos(Filtros(), "carga_confirmada"))["items"]


async def test_mantenciones_intervalos_comentarios_y_concurrencia(sesiones):
    async with sesiones() as db:
        ops = OperationsService(db, ACTOR)
        query = QueryService(db)
        vacia = await ops.crear_mantencion(MantencionCrear(bus_id=ACTOR))
        assert vacia["estado"] == "incompleta"
        assert (await query.ficha(ACTOR))["proxima_mantencion"] is None
        editada = await ops.editar_mantencion(
            vacia["id"],
            MantencionEditar(
                version=0,
                fecha=hoy() - timedelta(days=10),
                kilometraje=100000,
                estado="completa",
            ),
        )
        with pytest.raises(ConflictException):
            await ops.editar_mantencion(
                vacia["id"], MantencionEditar(version=0, ot="desactualizado")
            )
        await ops.comentar(editada["id"], Comentario(comentario="Comentario de prueba"))
        resultado = await ops.intervalo(
            ACTOR, IntervaloEditar(version=0, intervalo_mantencion_km=50000)
        )
        assert resultado["version"] > 0
        assert (await query.ficha(ACTOR))["proxima_mantencion"] == 150000
        historia = await query.historial(Filtros(bus_id=ACTOR))
        assert historia["items"][0]["proxima_mantencion"] == 150000
        await ops.editar_mantencion(
            editada["id"], MantencionEditar(version=1, activa=False)
        )
        assert (await query.ficha(ACTOR))["proxima_mantencion"] is None
        await ops.eliminar_mantencion(editada["id"], 2)
        eventos = await query.eventos(Filtros(bus_id=ACTOR))
        assert any(e["tipo"] == "mantencion_eliminada" for e in eventos["items"])


async def test_edicion_reevalua_fecha_y_kilometraje(sesiones):
    async with sesiones() as db:
        ops = OperationsService(db, ACTOR)
        servicio = ImportService(db, ACTOR)
        query = QueryService(db)
        await ops.crear_mantencion(
            MantencionCrear(
                bus_id=ACTOR, fecha=hoy() - timedelta(days=30), kilometraje=100000
            )
        )
        resultado = await servicio.confirmar(borrador("90000"))
        lectura_id = (await servicio.repo.registros_carga(db, resultado["carga_id"]))[
            0
        ].id
        lectura = await db.get(Km, lectura_id)
        assert lectura.estado == "pendiente"
        assert (await query.ficha(ACTOR))["ultimo_confirmado"] == 100000
        editada = await ops.editar_lectura(
            lectura_id, LecturaEditar(version=0, kilometraje=110000)
        )
        assert editada["estado"] == "aceptado"
        with pytest.raises(BusinessRuleException):
            await ops.editar_lectura(
                lectura_id, LecturaEditar(version=1, kilometraje=120000)
            )
        resultado = await servicio.confirmar(borrador("120000", "31-13-26"))
        lectura_id = (await servicio.repo.registros_carga(db, resultado["carga_id"]))[
            0
        ].id
        lectura = await db.get(Km, lectura_id)
        assert lectura.fecha is None
        editada = await ops.editar_lectura(
            lectura_id, LecturaEditar(version=0, fecha=hoy() + timedelta(days=1))
        )
        assert editada["estado"] == "pendiente"
        editada = await ops.editar_lectura(
            lectura_id, LecturaEditar(version=1, fecha=hoy() - timedelta(days=1))
        )
        assert (
            editada["estado"] == "pendiente"
        )  # posterior confirmado tiene un kilometraje inferior


async def test_confirmacion_concurrente_y_rollback(sesiones):
    carga = borrador()

    async def confirmar():
        async with sesiones() as db:
            return await ImportService(db, ACTOR).confirmar(carga)

    a, b = await asyncio.wait_for(asyncio.gather(confirmar(), confirmar()), 20)
    assert a["carga_id"] == b["carga_id"]
    async with sesiones() as db:
        assert await db.scalar(select(func.count()).select_from(Km)) == 1
        servicio = ImportService(db, ACTOR)
        modificada = carga.model_copy(deep=True)
        modificada.filas[0].kilometraje = "151000"
        with pytest.raises(ConflictException):
            await servicio.confirmar(modificada)
        invalida = borrador("160000", "fecha inválida")
        invalida.filas[0].decision = "aceptar"
        with pytest.raises(BusinessRuleException):
            await servicio.confirmar(invalida)
        assert await db.scalar(select(func.count()).select_from(Km)) == 1


async def test_resultados_errores_y_paginacion(sesiones):
    async with sesiones() as db:
        servicio = ImportService(db, ACTOR)
        query = QueryService(db)
        filas = [
            FilaBorrador(
                fila=2, numero_bus="354", fecha=hoy().isoformat(), kilometraje="100000"
            ),
            FilaBorrador(
                fila=3,
                numero_bus="354",
                fecha=(hoy() - timedelta(days=10)).isoformat(),
                kilometraje="90000",
            ),
            FilaBorrador(fila=4, numero_bus="356", fecha="31-13-26", kilometraje="-5"),
            FilaBorrador(
                fila=5, numero_bus="99999", fecha=hoy().isoformat(), kilometraje="50"
            ),
            FilaBorrador(
                fila=6, numero_bus=None, fecha=hoy().isoformat(), kilometraje=None
            ),
        ]
        carga = Borrador(nombre_archivo="errores.xlsx", filas=filas)
        revision = await servicio.revisar(carga)
        assert [r.estado for r in revision.resultados] == [
            "aceptado",
            "ignorado",
            "error",
            "pendiente",
            "ignorado",
        ]
        confirmado = await servicio.confirmar(carga)
        assert confirmado["resumen"] == {
            "aceptado": 1,
            "error": 1,
            "pendiente": 1,
            "ignorado": 1,
        }
        listado = await query.eventos(Filtros(), "carga_confirmada")
        assert "revision" not in listado["items"][0]["metadatos"]
        detalle = await query.filas_carga(confirmado["carga_id"], Filtros(limit=2))
        assert detalle["total"] == 5 and len(detalle["items"]) == 2
        filtrado = await query.filas_carga(
            confirmado["carga_id"], Filtros(estado="error")
        )
        assert filtrado["total"] == 1
        repetida = await servicio.revisar(carga)
        assert repetida.resultados[0].estado == "duplicado"


async def test_proyeccion_y_limite_del_grafico(sesiones):
    async with sesiones() as db:
        ops = OperationsService(db, ACTOR)
        query = QueryService(db)
        from app.modules.control_mantenciones.services.domain import desplazar_mes

        inicio = desplazar_mes(hoy(), -6)
        await ops.crear_mantencion(
            MantencionCrear(
                bus_id=ACTOR, fecha=inicio - timedelta(days=10), kilometraje=100000
            )
        )
        await ops.crear_mantencion(
            MantencionCrear(
                bus_id=ACTOR, fecha=inicio + timedelta(days=10), kilometraje=110000
            )
        )
        for dias, km in [(14, 120000), (7, 121000), (0, 122000)]:
            await ops.crear_lectura(
                LecturaCrear(
                    bus_id=ACTOR, fecha=hoy() - timedelta(days=dias), kilometraje=km
                )
            )
        assert (await query.proyeccion(ACTOR))["disponible"]
        grafico = await query.grafico(ACTOR)
        assert grafico["puntos"][0]["fecha"] == inicio
        assert grafico["puntos"][0]["kilometraje"] == 105000
        assert grafico["puntos"][0]["id"] is None
        assert all(p["fecha"] >= inicio for p in grafico["puntos"])
