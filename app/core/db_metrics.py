"""Métricas de viajes a base de datos, aisladas por petición HTTP.

No conserva SQL ni parámetros: sólo cuenta ejecuciones y tiempo del driver para
detectar regresiones N+1 sin exponer información sensible en logs o headers.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import perf_counter
from typing import Optional


@dataclass
class DbRequestMetrics:
    round_trips: int = 0
    time_ms: float = 0.0
    _statement_started_at: Optional[float] = None
    user_cache: Optional[str] = None


_metrics_var: ContextVar[Optional[DbRequestMetrics]] = ContextVar(
    "db_request_metrics", default=None
)


def begin_request_metrics() -> Token:
    """Inicia un contador nuevo para la tarea/corutina de la petición."""
    return _metrics_var.set(DbRequestMetrics())


def end_request_metrics(token: Token) -> Optional[DbRequestMetrics]:
    """Obtiene la métrica actual y restaura el contexto anterior."""
    metrics = _metrics_var.get()
    _metrics_var.reset(token)
    return metrics


def before_statement() -> None:
    metrics = _metrics_var.get()
    if metrics is not None:
        metrics._statement_started_at = perf_counter()


def after_statement() -> None:
    metrics = _metrics_var.get()
    if metrics is not None:
        metrics.round_trips += 1
        if metrics._statement_started_at is not None:
            metrics.time_ms += (perf_counter() - metrics._statement_started_at) * 1000
            metrics._statement_started_at = None


def record_transaction() -> None:
    """Cuenta el COMMIT como viaje de red aunque no ejecute un cursor SQL."""
    metrics = _metrics_var.get()
    if metrics is not None:
        metrics.round_trips += 1


def mark_user_cache(result: str) -> None:
    """Anota sólo hit/miss para correlacionar el viaje de autenticación."""
    metrics = _metrics_var.get()
    if metrics is not None:
        metrics.user_cache = result
