from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.supervision.dtos.telegram_dto import TelegramNotificacionDTO, TelegramResultadoDTO
from app.modules.supervision.models import TelegramEnvio

MAX_INTENTOS = 3
RESERVA_TIMEOUT = timedelta(minutes=10)


class TelegramRepository:
    async def reservar(self, db: AsyncSession, envio: TelegramNotificacionDTO) -> tuple[int, int] | None:
        """El índice único arbitra entre procesos sin un SELECT previo."""
        insertar = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
        values = envio.model_dump(exclude={"parametros"}) | {"estado": "ENVIANDO"}
        stmt = insertar(TelegramEnvio).values(**values).on_conflict_do_nothing(index_elements=["clave"])
        reservado = (await db.execute(stmt.returning(TelegramEnvio.id, TelegramEnvio.intentos))).first()
        if reservado:
            return reservado.id, reservado.intentos
        return await self._reservar_reintento(db, envio)

    async def _reservar_reintento(self, db: AsyncSession, envio: TelegramNotificacionDTO) -> tuple[int, int] | None:
        ahora = datetime.now(timezone.utc)
        stmt = update(TelegramEnvio).where(
            TelegramEnvio.clave == envio.clave, TelegramEnvio.estado == "REINTENTABLE",
            TelegramEnvio.intentos < MAX_INTENTOS, TelegramEnvio.proximo_intento <= ahora,
        ).values(
            estado="ENVIANDO", intentos=TelegramEnvio.intentos + 1,
            proximo_intento=None, codigo_error=None, updated_at=ahora, mensaje=envio.mensaje,
        ).returning(TelegramEnvio.id, TelegramEnvio.intentos)
        reservado = (await db.execute(stmt)).first()
        return (reservado.id, reservado.intentos) if reservado else None

    async def registrar_resultado(self, db: AsyncSession, resultado: tuple[int, TelegramResultadoDTO]) -> None:
        envio_id, datos = resultado
        await db.execute(update(TelegramEnvio).where(TelegramEnvio.id == envio_id).values(**datos.model_dump()))

    async def expirar_reservas(self, db: AsyncSession) -> None:
        limite = datetime.now(timezone.utc) - RESERVA_TIMEOUT
        await db.execute(update(TelegramEnvio).where(
            TelegramEnvio.estado == "ENVIANDO", TelegramEnvio.updated_at < limite,
        ).values(estado="INCIERTO", codigo_error="RESERVA_EXPIRADA"))

    async def listar(self, db: AsyncSession, pagina: tuple[int, int]) -> list[TelegramEnvio]:
        skip, limit = pagina
        stmt = select(TelegramEnvio).order_by(TelegramEnvio.id.desc()).offset(skip).limit(limit)
        return list((await db.scalars(stmt)).all())
