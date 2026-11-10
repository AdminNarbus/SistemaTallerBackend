"""Atomicidad y traducción uniforme de conflictos de persistencia."""

from typing import Any

from functools import wraps
import logging

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictException

logger = logging.getLogger(__name__)


def atomic(method: Any) -> Any:
    @wraps(method)
    async def execute(self, *args, **kwargs) -> Any:
        try:
            result = await method(self, *args, **kwargs)
            await self.db.commit()
            return result
        except IntegrityError as error:
            await self.db.rollback()
            logger.warning(
                "Conflicto de integridad en control de mantenciones", exc_info=True
            )
            raise ConflictException(
                "El registro ya existe o cambió durante la operación. Recargue y vuelva a intentarlo."
            ) from error
        except Exception:
            await self.db.rollback()
            raise

    return execute
