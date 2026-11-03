from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.modules.dashboard.repository.bus_dashboard_repository import BusDashboardRepository
from app.modules.dashboard.repository.cronologia_repository import CronologiaRepository
from app.modules.dashboard.repository.dashboard_repository import DashboardRepository
from app.modules.dashboard.repository.filter_repository import FilterRepository
from app.modules.dashboard.services.bus_dashboard_service import BusDashboardService
from app.modules.dashboard.services.cronologia_service import CronologiaService
from app.modules.dashboard.services.dashboard_service import DashboardService, FilterService


def dashboard_service(db: AsyncSession = SessionDep):
    return DashboardService(DashboardRepository(db))


def bus_service(db: AsyncSession = SessionDep):
    return BusDashboardService(BusDashboardRepository(db))


def timeline_service(db: AsyncSession = SessionDep):
    return CronologiaService(CronologiaRepository(db), BusDashboardRepository(db))


def filter_service(db: AsyncSession = SessionDep):
    return FilterService(FilterRepository(db))


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


def paged_response(response, result):
    response.headers["X-Total-Count"] = str(result.data.total)
    return result
