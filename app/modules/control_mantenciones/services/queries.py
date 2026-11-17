"""Coordinación de consultas y cálculo de series para las pantallas."""

from typing import Any

from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.exceptions import NotFoundException
from app.modules.control_mantenciones.dtos.contracts import Filtros
from app.modules.control_mantenciones.repository.screens import ReadRepository
from app.modules.control_mantenciones.services.domain import (
    PASO_EJE_Y,
    desplazar_mes,
    hoy,
    proyectar,
)


class QueryService:
    def __init__(self, db: AsyncSession) -> Any:
        self.queries = ReadRepository(db)

    async def panel(self, filtros: Filtros) -> dict:
        return await self.queries.panel(filtros)

    async def ficha(self, bus_id: int) -> dict:
        registro = await self.queries.ficha(bus_id)
        if registro is None:
            raise NotFoundException(
                "No se encontró un bus activo con número de máquina."
            )
        return registro

    async def historial(self, filtros: Filtros) -> dict:
        return await self.queries.historial(filtros)

    async def eventos(self, filtros: Filtros, tipo: str | None = None) -> dict:
        return await self.queries.eventos(filtros, tipo)

    async def detalle(self, modelo: Any, identificador: int) -> dict:
        registro = await self.queries.detalle(modelo, identificador)
        if registro is None:
            raise NotFoundException("No se encontró el registro solicitado.")
        return registro

    async def detalle_carga(self, identificador: int) -> dict:
        registro = await self.queries.detalle_carga(identificador)
        if registro is None:
            raise NotFoundException("No se encontró la carga confirmada.")
        return registro

    async def filas_carga(self, identificador: int, filtros: Filtros) -> dict:
        await self.detalle_carga(identificador)
        return await self.queries.filas_carga(identificador, filtros)

    async def serie_periodo(self, filtros: Filtros) -> list[dict]:
        return await self.queries.serie_periodo(filtros)

    async def punto_anterior(self, bus_id: int, inicio: Any) -> dict | None:
        return await self.queries.punto_anterior(bus_id, inicio)

    async def proyeccion(self, bus_id: int) -> dict:
        ficha = await self.ficha(bus_id)
        filtros = Filtros(
            bus_id=bus_id,
            desde=hoy() - timedelta(days=settings.CONTROL_MANTENCIONES_VENTANA_DIAS),
        )
        registros = await self.serie_periodo(filtros)
        return proyectar(registros, ficha, settings.CONTROL_MANTENCIONES_VENTANA_DIAS)

    async def grafico(self, bus_id: int) -> dict:
        ficha = await self.ficha(bus_id)
        inicio = desplazar_mes(hoy(), -6)
        registros = await self.serie_periodo(Filtros(bus_id=bus_id, desde=inicio))
        puntos = [r for r in registros if r["estado"] == "aceptado"]
        anterior = await self.punto_anterior(bus_id, inicio)
        self.interpolar_limite(puntos, anterior, inicio)
        estimacion = await self.proyeccion(bus_id)
        ejes = self.ejes_grafico(puntos, ficha, estimacion)
        return {
            **ejes,
            "inicio": inicio,
            "puntos": puntos,
            "punto_vencido": self.punto_vencido(puntos, ficha["proxima_mantencion"]),
            "proyeccion": estimacion,
            "proxima_mantencion": ficha["proxima_mantencion"],
        }

    def punto_vencido(
        self, puntos: list[dict], objetivo: Decimal | None
    ) -> dict | None:
        if objetivo is None or not puntos or puntos[-1]["kilometraje"] < objetivo:
            return None
        for anterior, actual in zip(puntos, puntos[1:]):
            if (
                anterior["kilometraje"] <= objetivo <= actual["kilometraje"]
                and actual["kilometraje"] > anterior["kilometraje"]
            ):
                fraccion = (objetivo - anterior["kilometraje"]) / (
                    actual["kilometraje"] - anterior["kilometraje"]
                )
                return {
                    "fecha": anterior["fecha"]
                    + timedelta(
                        days=float(
                            fraccion * (actual["fecha"] - anterior["fecha"]).days
                        )
                    ),
                    "kilometraje": objetivo,
                    "tipo": "mantencion_vencida",
                }
        return None

    def interpolar_limite(
        self, puntos: list[dict], anterior: dict | None, inicio: Any
    ) -> None:
        if not anterior or not puntos or puntos[0]["fecha"] <= inicio:
            return
        factor = (
            Decimal((inicio - anterior["fecha"]).days)
            / (puntos[0]["fecha"] - anterior["fecha"]).days
        )
        km = anterior["kilometraje"] + factor * (
            puntos[0]["kilometraje"] - anterior["kilometraje"]
        )
        puntos.insert(
            0,
            {
                "id": None,
                "tipo": "limite",
                "fecha": inicio,
                "kilometraje": km.quantize(Decimal("0.01")),
                "interpolado": True,
            },
        )

    def ejes_grafico(self, puntos: list[dict], ficha: dict, estimacion: dict) -> dict:
        inicio = desplazar_mes(hoy(), -6)
        final = max(hoy(), estimacion.get("fecha", hoy()))
        ticks, mes = [], 0
        while desplazar_mes(inicio, mes) <= final:
            ticks.append(desplazar_mes(inicio, mes))
            mes += 1
        valores = [p["kilometraje"] for p in puntos]
        if ficha["proxima_mantencion"] is not None:
            valores.append(ficha["proxima_mantencion"])
        minimo = (
            (min(valores) / PASO_EJE_Y).to_integral_value(rounding=ROUND_FLOOR)
            * PASO_EJE_Y
            if valores
            else Decimal(0)
        )
        maximo = (
            ((max(valores) / PASO_EJE_Y).to_integral_value(rounding=ROUND_CEILING) + 1)
            * PASO_EJE_Y
            if valores
            else PASO_EJE_Y
        )
        return {
            "fin": final,
            "divisiones_mensuales": ticks,
            "paso_kilometraje": PASO_EJE_Y,
            "minimo_kilometraje": minimo,
            "maximo_kilometraje": maximo,
        }
