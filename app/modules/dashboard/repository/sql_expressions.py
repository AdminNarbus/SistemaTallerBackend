"""Expresiones PostgreSQL; compilación SQLite para las pruebas aisladas."""

from sqlalchemy import Date, DateTime, Float, String
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement


class LocalDay(FunctionElement):
    type = Date()
    inherit_cache = True


class MonthKey(FunctionElement):
    type = String()
    inherit_cache = True


class WeekKey(FunctionElement):
    type = String()
    inherit_cache = True


class BusKey(FunctionElement):
    type = String()
    inherit_cache = True


class Normalized(FunctionElement):
    type = String()
    inherit_cache = True


class Hours(FunctionElement):
    type = Float()
    inherit_cache = True


class EndOfDay(FunctionElement):
    type = DateTime(timezone=True)
    inherit_cache = True


class Median(FunctionElement):
    type = Float()
    inherit_cache = True


def argument(element, compiler, **kwargs):
    return compiler.process(element.clauses, **kwargs)


@compiles(LocalDay, "postgresql")
def pg_day(element, compiler, **kwargs):
    return f"({argument(element, compiler, **kwargs)} AT TIME ZONE 'America/Santiago')::date"


@compiles(MonthKey, "postgresql")
def pg_month(element, compiler, **kwargs):
    return f"to_char({argument(element, compiler, **kwargs)} AT TIME ZONE 'America/Santiago', 'YYYY-MM')"


@compiles(WeekKey, "postgresql")
def pg_week(element, compiler, **kwargs):
    return f"to_char(date_trunc('week', {argument(element, compiler, **kwargs)} AT TIME ZONE 'America/Santiago'), 'YYYY-MM-DD')"


@compiles(BusKey, "postgresql")
def pg_bus(element, compiler, **kwargs):
    value = f"regexp_replace(btrim(cast({argument(element, compiler, **kwargs)} as text)), '^#\\s*', '')"
    return f"nullif(regexp_replace({value}, '^0+(?=[0-9])', ''), '')"


@compiles(Normalized, "postgresql")
def pg_normalized(element, compiler, **kwargs):
    value = f"normalize(cast({argument(element, compiler, **kwargs)} as text), NFKD)"
    ascii_value = f"regexp_replace({value}, '[^' || chr(1) || '-' || chr(127) || ']', '', 'g')"
    return f"nullif(btrim(regexp_replace(lower({ascii_value}), '[^a-z0-9]+', ' ', 'g')), '')"


@compiles(Hours, "postgresql")
def pg_hours(element, compiler, **kwargs):
    start, end = [compiler.process(value, **kwargs) for value in element.clauses]
    return f"(extract(epoch from ({end} - {start})) / 3600.0)"


@compiles(EndOfDay, "postgresql")
def pg_end(element, compiler, **kwargs):
    day = argument(element, compiler, **kwargs)
    return f"((cast({day} as date) + interval '1 day') AT TIME ZONE 'America/Santiago' - interval '1 microsecond')"


@compiles(Median, "postgresql")
def pg_median(element, compiler, **kwargs):
    return f"percentile_cont(0.5) within group (order by {argument(element, compiler, **kwargs)})"


def sqlite_function(element, compiler, **kwargs):
    return f"dashboard_{type(element).__name__.lower()}({argument(element, compiler, **kwargs)})"


for expression in (LocalDay, MonthKey, WeekKey, BusKey, Normalized, Hours, EndOfDay, Median):
    compiles(expression, "sqlite")(sqlite_function)
