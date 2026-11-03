from dataclasses import dataclass

from sqlalchemy import Float, Numeric, case, cast, func, select

from app.modules.dashboard.repository.order_queries import OrderQueries
from app.modules.dashboard.repository.relations import Relations, S
from app.modules.dashboard.repository.sql_expressions import LocalDay

def count_when(condition):
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def percentage(numerator, denominator):
    return cast(
        func.round(cast(numerator * 100.0 / func.nullif(denominator, 0), Numeric), 2), Float
    )


def valid_duration(value):
    return case((value >= 0, value), else_=None)


@dataclass(frozen=True)
class QueryPage:
    items: list[dict]
    total: int
    skip: int
    limit: int

    def as_dict(self):
        return {"items": self.items, "total": self.total, "skip": self.skip, "limit": self.limit}


class ReadRepository:
    def __init__(self, db):
        self.db = db
        self.relations = Relations()
        self.queries = OrderQueries(self.relations)

    async def rows(self, statement):
        with self.db.no_autoflush:
            result = await self.db.execute(statement)
        return [dict(row) for row in result.mappings()]

    async def one(self, statement):
        rows = await self.rows(statement)
        return rows[0]

    async def page(self, statement, filters):
        count = select(func.count().label("total")).select_from(statement.order_by(None).subquery())
        total = (await self.one(count))["total"]
        items = await self.rows(statement.offset(filters.skip).limit(filters.limit))
        return QueryPage(items, total, filters.skip, filters.limit)

    async def reference(self):
        result = await self.one(select(func.max(LocalDay(S.c.fecha_creacion)).label("day")))
        return result["day"]
