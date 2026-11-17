"""Expresiones SQL del panel y del historial preventivo."""

from typing import Any

from datetime import date

from sqlalchemy import (
    Integer,
    Numeric,
    String,
    and_,
    case,
    cast,
    func,
    literal,
    or_,
    select,
    union_all,
)
from app.modules.buses.models.bus import Bus
from app.modules.control_mantenciones.models.entities import (
    ControlEvento as Evento,
    ControlKilometraje as Km,
    ControlMantencion as Mant,
)
from app.modules.control_mantenciones.repository.records import registros_validos


def intervalo_sql() -> Any:
    marca = func.lower(func.trim(Bus.marca))
    mercedes = case((Bus.n_bus.in_(["354", "396"]), 40000), else_=60000)
    regla = case(
        (marca.in_(["sc", "scania"]), 50000),
        (marca == "volvo", 40000),
        (marca.in_(["mb", "mercedes", "mercedes-benz", "mercedes benz"]), mercedes),
        else_=None,
    )
    return func.coalesce(Bus.intervalo_mantencion_km, cast(regla, Numeric(12, 2)))


def numero_ordenado(columna: Any) -> Any:
    return case((columna.op("~")("^[0-9]+$"), cast(columna, Numeric)), else_=None)


def ultima_fecha(registros: Any) -> Any:
    return (
        select(registros.c.bus_id, func.max(registros.c.fecha).label("fecha"))
        .group_by(registros.c.bus_id)
        .cte("ultima")
    )


def kilometraje_vigente(registros: Any, ultima: Any) -> Any:
    columnas = [
        registros.c.bus_id,
        func.max(registros.c.kilometraje).label("km"),
        func.count(func.distinct(registros.c.kilometraje)).label("variantes"),
    ]
    condicion = and_(
        registros.c.bus_id == ultima.c.bus_id, registros.c.fecha == ultima.c.fecha
    )
    return (
        select(*columnas)
        .join(ultima, condicion)
        .group_by(registros.c.bus_id)
        .cte("vigente")
    )


def fecha_mantencion() -> Any:
    valido = [
        Mant.activa.is_(True),
        Mant.fecha.is_not(None),
        Mant.kilometraje.is_not(None),
    ]
    return (
        select(Mant.bus_id, func.max(Mant.fecha).label("fecha"))
        .where(*valido)
        .group_by(Mant.bus_id)
        .cte("mant_fecha")
    )


def kilometraje_mantencion(fecha: Any) -> Any:
    columnas = [
        Mant.bus_id,
        func.max(Mant.kilometraje).label("km"),
        func.count(func.distinct(Mant.kilometraje)).label("variantes"),
    ]
    condicion = and_(Mant.bus_id == fecha.c.bus_id, Mant.fecha == fecha.c.fecha)
    return (
        select(*columnas)
        .join(fecha, condicion)
        .where(Mant.activa.is_(True))
        .group_by(Mant.bus_id)
        .cte("mant")
    )


def pendientes_sql(ultima: Any) -> Any:
    condicion = or_(
        Km.fecha.is_(None), ultima.c.fecha.is_(None), Km.fecha >= ultima.c.fecha
    )
    return (
        select(func.count())
        .select_from(Km)
        .where(Km.bus_id == Bus.id, Km.estado == "pendiente", condicion)
        .correlate(Bus, ultima)
        .scalar_subquery()
    )


def corte_conflicto(tablas: Any) -> Any:
    pendiente = (
        select(func.min(Km.fecha))
        .where(
            Km.bus_id == Bus.id,
            Km.estado == "pendiente",
            or_(
                Km.fecha.is_(None),
                tablas["ultima"].c.fecha.is_(None),
                Km.fecha >= tablas["ultima"].c.fecha,
            ),
        )
        .correlate(Bus, tablas["ultima"])
        .scalar_subquery()
    )
    lectura = case(
        (tablas["vigente"].c.variantes > 1, tablas["ultima"].c.fecha), else_=None
    )
    mantencion = case(
        (tablas["mant"].c.variantes > 1, tablas["mant_fecha"].c.fecha), else_=None
    )
    return func.coalesce(func.least(pendiente, lectura, mantencion), literal(date.max))


def ultimo_confirmado(tablas: Any) -> Any:
    registros = tablas["registros"]
    diario = (
        select(
            registros.c.bus_id,
            registros.c.fecha,
            func.max(registros.c.kilometraje).label("km"),
        )
        .group_by(registros.c.bus_id, registros.c.fecha)
        .having(func.count(func.distinct(registros.c.kilometraje)) == 1)
        .cte("diario_confirmado")
    )
    previo = (
        select(diario.c.km)
        .where(diario.c.bus_id == Bus.id, diario.c.fecha < corte_conflicto(tablas))
        .order_by(diario.c.fecha.desc())
        .limit(1)
    )
    return previo.correlate(
        Bus, tablas["ultima"], tablas["vigente"], tablas["mant"], tablas["mant_fecha"]
    ).scalar_subquery()


def tablas_panel() -> Any:
    registros = registros_validos()
    ultima = ultima_fecha(registros)
    mant_fecha = fecha_mantencion()
    return {
        "registros": registros,
        "ultima": ultima,
        "vigente": kilometraje_vigente(registros, ultima),
        "mant_fecha": mant_fecha,
        "mant": kilometraje_mantencion(mant_fecha),
    }


def calculos_panel(tablas: Any) -> Any:
    vigente, mant = tablas["vigente"], tablas["mant"]
    conflicto = or_(
        func.coalesce(vigente.c.variantes, 0) > 1,
        func.coalesce(mant.c.variantes, 0) > 1,
        pendientes_sql(tablas["ultima"]) > 0,
    )
    km = case((conflicto, None), else_=vigente.c.km)
    proxima = case(
        (func.coalesce(mant.c.variantes, 0) <= 1, mant.c.km + intervalo_sql()),
        else_=None,
    )
    return conflicto, km, proxima


def columnas_panel(tablas: Any) -> Any:
    conflicto, km, proxima = calculos_panel(tablas)
    version = (
        select(func.coalesce(func.max(Evento.id), 0))
        .where(Evento.bus_id == Bus.id, Evento.tipo == "intervalo_cambiado")
        .correlate(Bus)
        .scalar_subquery()
    )
    return [
        Bus.id.label("bus_id"),
        Bus.n_bus.label("numero_bus"),
        Bus.patente,
        Bus.marca,
        Bus.servicio,
        intervalo_sql().label("intervalo"),
        version.label("version_intervalo"),
        km.label("kilometraje_actual"),
        case(
            (conflicto, ultimo_confirmado(tablas)), else_=tablas["vigente"].c.km
        ).label("ultimo_confirmado"),
        tablas["ultima"].c.fecha.label("ultima_lectura"),
        tablas["mant_fecha"].c.fecha.label("ultima_mantencion"),
        proxima.label("proxima_mantencion"),
        (proxima - km).label("restantes"),
        conflicto.label("conflicto"),
    ]


def panel_base() -> Any:
    tablas = tablas_panel()
    consulta = select(*columnas_panel(tablas)).select_from(Bus)
    for nombre in ("ultima", "vigente", "mant_fecha", "mant"):
        tabla = tablas[nombre]
        consulta = consulta.outerjoin(tabla, tabla.c.bus_id == Bus.id)
    return consulta.where(
        Bus.is_active.is_(True), Bus.n_bus.is_not(None), func.trim(Bus.n_bus) != ""
    )


def estados_panel(base: Any, hoy: Any, dias_recientes: Any) -> Any:
    restantes = base.c.restantes
    estado_km = case(
        (restantes.is_(None), "Sin datos suficientes para calcular"),
        (restantes < 0, "Vencida"),
        (restantes <= 8000, "Crítica"),
        (restantes <= 20000, "Próxima"),
        else_="Al día",
    )
    antigua = or_(
        base.c.ultima_lectura.is_(None),
        (literal(hoy) - base.c.ultima_lectura) > dias_recientes,
    )
    estado = case(
        (base.c.conflicto, "Requiere revisión"),
        (antigua, "Sin lectura reciente"),
        else_=estado_km,
    )
    return estado_km, antigua, estado


def filtrar_panel(consulta: Any, base: Any, filtros: Any) -> Any:
    if filtros.bus_id:
        consulta = consulta.where(base.c.bus_id == filtros.bus_id)
    if filtros.buscar:
        consulta = consulta.where(
            or_(
                base.c.numero_bus.ilike(f"%{filtros.buscar}%"),
                base.c.patente.ilike(f"%{filtros.buscar}%"),
            )
        )
    return consulta


def panel_consulta(filtros: Any, hoy: Any, dias_recientes: Any) -> Any:
    base = panel_base().subquery()
    estado_km, antigua, estado = estados_panel(base, hoy, dias_recientes)
    consulta = select(
        base,
        estado_km.label("estado_kilometraje"),
        estado.label("estado"),
        antigua.label("sin_lectura_reciente"),
    )
    consulta = filtrar_panel(consulta, base, filtros)
    if filtros.estado:
        consulta = consulta.where(
            or_(estado == filtros.estado, estado_km == filtros.estado)
        )
    orden = {
        "restantes": base.c.restantes.asc().nullslast(),
        "fecha": base.c.ultima_lectura.desc().nullslast(),
    }
    return consulta.order_by(
        orden.get(
            filtros.ordenar, numero_ordenado(base.c.numero_bus).asc().nullslast()
        ),
        base.c.numero_bus,
        base.c.bus_id,
    )


def columnas_lecturas() -> Any:
    return [
        Km.id,
        Km.bus_id,
        literal("kilometraje").label("tipo"),
        Km.fecha,
        Km.kilometraje,
        Km.estado,
        literal(None, String).label("tipo_mantencion"),
        literal(None, String).label("certificado"),
        literal(None, String).label("ot"),
        Km.origen,
        Km.evento_carga_id,
        Km.version,
        literal(None, Numeric).label("proxima_mantencion"),
        literal(None).label("activa"),
    ]


def columnas_mantenciones() -> Any:
    return [
        Mant.id,
        Mant.bus_id,
        literal("mantencion"),
        Mant.fecha,
        Mant.kilometraje,
        Mant.estado,
        Mant.tipo_mantencion,
        Mant.certificado,
        Mant.ot,
        literal("manual"),
        literal(None, Integer),
        Mant.version,
        Mant.kilometraje + intervalo_sql(),
        Mant.activa,
    ]


def registros_historial(tipo: Any) -> Any:
    lectura = select(*columnas_lecturas())
    mantencion = select(*columnas_mantenciones()).join(Bus, Bus.id == Mant.bus_id)
    if tipo == "kilometraje":
        return lectura.subquery()
    return (
        mantencion.subquery()
        if tipo == "mantencion"
        else union_all(lectura, mantencion).subquery()
    )


def filtros_historial(registros: Any, filtros: Any) -> Any:
    condiciones = []
    for campo in ("bus_id", "estado"):
        if (valor := getattr(filtros, campo)) is not None:
            condiciones.append(getattr(registros.c, campo) == valor)
    if filtros.desde:
        condiciones.append(registros.c.fecha >= filtros.desde)
    if filtros.hasta:
        condiciones.append(registros.c.fecha <= filtros.hasta)
    if filtros.buscar:
        condiciones.append(
            or_(
                Bus.n_bus.ilike(f"%{filtros.buscar}%"),
                Bus.patente.ilike(f"%{filtros.buscar}%"),
            )
        )
    return condiciones


def historial_consulta(filtros: Any) -> Any:
    registros = registros_historial(filtros.tipo)
    consulta = select(registros, Bus.n_bus.label("numero_bus"), Bus.patente).outerjoin(
        Bus, Bus.id == registros.c.bus_id
    )
    consulta = consulta.where(*filtros_historial(registros, filtros))
    return consulta.order_by(
        numero_ordenado(Bus.n_bus).asc().nullslast(),
        Bus.n_bus,
        registros.c.fecha.desc().nullslast(),
        registros.c.id.desc(),
    )
