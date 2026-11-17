"""Exportación paginada en memoria; no almacena el archivo generado."""

from typing import Any

import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from app.core.config import settings
from app.modules.control_mantenciones.repository.queries import (
    historial_consulta,
    panel_consulta,
)
from app.modules.control_mantenciones.services.domain import hoy
from app.modules.control_mantenciones.repository.screens import ReadRepository

TITULOS = {
    "bus_id": "Identificador bus",
    "numero_bus": "Bus",
    "tipo": "Registro",
    "fecha": "Fecha",
    "kilometraje": "Kilometraje",
    "estado": "Estado",
    "proxima_mantencion": "Próxima mantención",
    "created_at": "Fecha de creación",
    "updated_at": "Última actualización",
    "usuario_id": "Usuario",
    "kilometraje_actual": "Km actual",
    "ultimo_confirmado": "Último confirmado",
    "ultima_lectura": "Última lectura",
    "ultima_mantencion": "Última mantención",
    "restantes": "Restantes",
    "intervalo": "Intervalo",
    "patente": "Patente",
    "marca": "Marca",
    "servicio": "Servicio",
    "tipo_mantencion": "Tipo de mantención",
    "certificado": "Certificado",
    "ot": "OT",
    "origen": "Origen",
    "evento_carga_id": "Carga",
    "version": "Versión",
    "activa": "Activa",
    "comentario": "Comentario",
    "valores_anteriores": "Valores anteriores",
    "valores_nuevos": "Valores nuevos",
    "metadatos": "Detalle",
}


def celda(valor: Any) -> Any:
    if isinstance(valor, (date, datetime)):
        return valor.strftime(
            "%d-%m-%Y %H:%M:%S" if isinstance(valor, datetime) else "%d-%m-%Y"
        )
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False, default=str)
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, str) and valor.startswith(("=", "+", "-", "@")):
        return "'" + valor
    return valor


def agregar(sheet: Any, filas: Any) -> Any:
    for fila in filas:
        sheet.append([celda(valor) for valor in fila])


def finalizar(libro: Any) -> bytes:
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


async def exportar(db: Any, filtros: Any, area: str, estados_panel: str = "") -> bytes:
    from openpyxl import Workbook

    servicio = ReadRepository(db)
    if area == "panel":
        consulta = panel_consulta(
            filtros, hoy(), settings.CONTROL_MANTENCIONES_DIAS_RECIENTES
        )
    elif area in {"eventos", "cargas"}:
        consulta = servicio.consulta_eventos(
            filtros, "carga_confirmada" if area == "cargas" else None
        )
    else:
        consulta = historial_consulta(filtros)
    if area == "panel":
        from sqlalchemy import select
        estados = [x for x in estados_panel.split(",") if x in {"Vencida", "Crítica", "Próxima", "Al día"}]
        if estados_panel and len(estados) != len(estados_panel.split(",")):
            raise ValueError("Filtro de estados inválido")
        base = consulta.subquery()
        consulta = select(base.c.numero_bus, base.c.marca, base.c.patente,
                          base.c.servicio, base.c.ultima_lectura, base.c.kilometraje_actual)
        if estados:
            consulta = consulta.where(base.c.estado_kilometraje.in_(estados)).order_by(base.c.restantes.asc().nullslast(), base.c.numero_bus, base.c.bus_id)
        else:
            consulta = consulta.order_by(base.c.numero_bus, base.c.bus_id)
    libro = Workbook(write_only=True)
    hoja = libro.create_sheet("Reporte")
    resultado = await db.stream(consulta)
    if area == "panel":
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.styles import Font, PatternFill
        encabezado = []
        for titulo in ("Número de bus", "Marca", "Patente", "Ruta", "Última lectura", "Kilometraje actual"):
            celda_titulo = WriteOnlyCell(hoja, value=titulo)
            celda_titulo.fill = PatternFill(fill_type="solid", fgColor="FFFF00")
            celda_titulo.font = Font(bold=True)
            encabezado.append(celda_titulo)
        hoja.append(encabezado)
    else:
        await asyncio.to_thread(agregar, hoja, [[TITULOS.get(k, k.replace("_", " ").capitalize()) for k in resultado.keys()]])
    while filas := await resultado.fetchmany(1000):
        await asyncio.to_thread(agregar, hoja, filas)
    return await asyncio.to_thread(finalizar, libro)
