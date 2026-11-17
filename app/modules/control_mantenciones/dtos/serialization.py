from typing import Any
from decimal import Decimal
from fastapi.encoders import jsonable_encoder


def snapshot(registro: Any) -> dict:
    return jsonable_encoder(
        {c.name: getattr(registro, c.name) for c in registro.__table__.columns},
        custom_encoder={Decimal: str},
    )
