import asyncio
import time
from collections import defaultdict, deque
from typing import Deque, DefaultDict

from app.core.exceptions import BusinessRuleException


class AuthRateLimiter:
    """Rate limit básico por proceso para endpoints públicos de autenticación.

    El límite evita abuso accidental y fuerza bruta en cada instancia. Para un
    despliegue horizontal debe complementarse con un rate limit en gateway/WAF.
    """

    def __init__(self) -> None:
        self._attempts: DefaultDict[str, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        bucket_key = f"{key}:{limit}:{window_seconds}"
        async with self._lock:
            attempts = self._attempts[bucket_key]
            cutoff = now - window_seconds
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= limit:
                raise BusinessRuleException(
                    "Demasiados intentos. Espere antes de volver a intentarlo.",
                    status_code=429,
                )
            attempts.append(now)


auth_rate_limiter = AuthRateLimiter()

__all__ = ["AuthRateLimiter", "auth_rate_limiter"]
