import logging
from datetime import datetime
from typing import Any, List, Optional, Set
from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth.models.usuario import Usuario
from app.modules.auth.models.rol import Rol
from app.modules.auth.constants import RolUsuario
from app.modules.taller.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta, TallerSolicitudPautaMecanico
from app.modules.taller.models.taller_solicitud import TallerSolicitud
from app.modules.taller.models.taller_solicitud_comentario import TallerSolicitudComentario

logger = logging.getLogger(__name__)


class PautaRepository:
    """
    Repositorio de Persistencia Pura (SQL) para el checklist de pauta preventiva de taller.
    Responsabilidad exclusiva: Consultas y persistencia de catálogo y respuestas de pauta.
    No gestiona lógica de negocio ni realiza commits de transacciones.
    """

    async def lock_solicitud(self, db: AsyncSession, solicitud_id: int) -> bool:
        stmt = select(TallerSolicitud.id).where(TallerSolicitud.id == solicitud_id).with_for_update()
        return (await db.execute(stmt)).scalar_one_or_none() is not None

    async def get_mecanicos_activos(self, db: AsyncSession, ids: Set[int]) -> dict[int, str]:
        stmt = select(Usuario.id, Usuario.nombre, Usuario.apellido).join(Rol, Usuario.rol_id == Rol.id).where(
            Usuario.id.in_(ids), Usuario.is_active.is_(True), Rol.nombre == RolUsuario.MECANICO.value,
        )
        rows = (await db.execute(stmt)).all()
        return {row.id: f"{row.nombre or ''} {row.apellido or ''}".strip() for row in rows}

    async def get_progreso(self, db: AsyncSession, solicitud_id: int) -> dict:
        stmt = (
            select(func.count(PautaTallerItem.id).label("total"),
                   func.count(TallerSolicitudPauta.id).label("revisadas"))
            .select_from(PautaTallerItem)
            .outerjoin(TallerSolicitudPauta, and_(
                TallerSolicitudPauta.item_id == PautaTallerItem.id,
                TallerSolicitudPauta.solicitud_id == solicitud_id,
            ))
            .where(PautaTallerItem.is_active.is_(True))
        )
        return dict((await db.execute(stmt)).mappings().one())

    async def eliminar_respuestas(self, db: AsyncSession, solicitud_id: int, item_ids: List[int]) -> None:
        respuestas = select(TallerSolicitudPauta.id).where(
            TallerSolicitudPauta.solicitud_id == solicitud_id, TallerSolicitudPauta.item_id.in_(item_ids),
        )
        await db.execute(delete(TallerSolicitudPautaMecanico).where(
            TallerSolicitudPautaMecanico.pauta_id.in_(respuestas),
        ))
        stmt = delete(TallerSolicitudPauta).where(
            TallerSolicitudPauta.solicitud_id == solicitud_id,
            TallerSolicitudPauta.item_id.in_(item_ids),
        )
        await db.execute(stmt)

    async def registrar_gestion(self, db: AsyncSession, comentario: TallerSolicitudComentario) -> None:
        db.add(comentario)
        await db.execute(
            update(TallerSolicitud)
            .where(TallerSolicitud.id == comentario.solicitud_id)
            .values(fecha_actualizacion=comentario.fecha_registro)
        )

    async def get_pauta_items(self, db: AsyncSession) -> List[PautaTallerItem]:
        """Retorna los ítems activos de la pauta preventiva ordenados por orden e ID."""
        stmt = (
            select(PautaTallerItem)
            .where(PautaTallerItem.is_active == True)
            .order_by(PautaTallerItem.orden.asc(), PautaTallerItem.id.asc())
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_pauta_items_by_ids(self, db: AsyncSession, item_ids: List[int]) -> Set[int]:
        """Retorna el conjunto de IDs válidos para una lista de ítems solicitada."""
        stmt = select(PautaTallerItem.id).where(
            PautaTallerItem.id.in_(item_ids), PautaTallerItem.is_active.is_(True)
        )
        res = await db.execute(stmt)
        return set(res.scalars().all())

    async def get_pauta_respuestas_by_solicitud(
        self, db: AsyncSession, solicitud_id: int
    ) -> List[TallerSolicitudPauta]:
        """Obtiene las respuestas registradas de pauta preventiva para una solicitud."""
        stmt = (
            select(TallerSolicitudPauta)
            .where(TallerSolicitudPauta.solicitud_id == solicitud_id)
            .options(
                selectinload(TallerSolicitudPauta.item),
                selectinload(TallerSolicitudPauta.mecanico),
                selectinload(TallerSolicitudPauta.revisores).joinedload(TallerSolicitudPautaMecanico.mecanico),
            )
        )
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_pauta_resumen(
        self, db: AsyncSession, solicitud_id: int
    ) -> tuple[int, List[dict]]:
        """
        Retorna catálogo/respuestas y carga sus ejecutores en lote, en hasta 2 consultas SQL.
        """
        stmt = (
            select(
                PautaTallerItem.id.label("item_id"),
                PautaTallerItem.categoria.label("item_categoria"),
                PautaTallerItem.item.label("item_nombre"),
                PautaTallerItem.orden.label("item_orden"),
                TallerSolicitudPauta.id.label("id"),
                TallerSolicitudPauta.solicitud_id.label("solicitud_id"),
                TallerSolicitudPauta.estado.label("estado"),
                TallerSolicitudPauta.observacion.label("observacion"),
                TallerSolicitudPauta.mecanico_id.label("mecanico_id"),
                TallerSolicitudPauta.fecha_registro.label("fecha_registro"),
                Usuario.nombre.label("mecanico_nombre"),
                Usuario.apellido.label("mecanico_apellido"),
            )
            .select_from(PautaTallerItem)
            .outerjoin(
                TallerSolicitudPauta,
                and_(
                    TallerSolicitudPauta.item_id == PautaTallerItem.id,
                    TallerSolicitudPauta.solicitud_id == solicitud_id,
                ),
            )
            .outerjoin(Usuario, Usuario.id == TallerSolicitudPauta.mecanico_id)
            .where(PautaTallerItem.is_active == True)
            .order_by(PautaTallerItem.orden.asc(), PautaTallerItem.id.asc())
        )
        res = await db.execute(stmt)
        rows = res.all()

        total_items = len(rows)
        respuestas = []
        for r in rows:
            if r.id is not None:
                mec_nom = None
                if r.mecanico_nombre:
                    mec_nom = f"{r.mecanico_nombre} {r.mecanico_apellido or ''}".strip()
                respuestas.append({
                    "id": r.id,
                    "solicitud_id": r.solicitud_id,
                    "item_id": r.item_id,
                    "item_categoria": r.item_categoria,
                    "item_nombre": r.item_nombre,
                    "estado": r.estado,
                    "observacion": r.observacion,
                    "mecanico_id": r.mecanico_id,
                    "mecanico_nombre": mec_nom,
                    "fecha_registro": r.fecha_registro,
                })
        revisores = await self.get_revisores(db, [respuesta["id"] for respuesta in respuestas])
        return total_items, [dict(respuesta, mecanicos=revisores.get(respuesta["id"], []))
                             for respuesta in respuestas]

    async def get_revisores(self, db: AsyncSession, pauta_ids: List[int]) -> dict[int, list[dict]]:
        if not pauta_ids:
            return {}
        stmt = select(TallerSolicitudPautaMecanico.pauta_id, Usuario.id, Usuario.nombre, Usuario.apellido).join(
            Usuario, Usuario.id == TallerSolicitudPautaMecanico.mecanico_id,
        ).where(TallerSolicitudPautaMecanico.pauta_id.in_(pauta_ids)).order_by(Usuario.id)
        result = {}
        for row in (await db.execute(stmt)).all():
            result.setdefault(row.pauta_id, []).append(
                {"id": row.id, "nombre": f"{row.nombre or ''} {row.apellido or ''}".strip()},
            )
        return result

    async def reemplazar_revisores(self, db: AsyncSession, solicitud_id: int, respuestas: List[dict]) -> None:
        stmt = select(TallerSolicitudPauta.id, TallerSolicitudPauta.item_id).where(
            TallerSolicitudPauta.solicitud_id == solicitud_id,
            TallerSolicitudPauta.item_id.in_([r["item_id"] for r in respuestas]),
        )
        pauta_ids = {row.item_id: row.id for row in (await db.execute(stmt)).all()}
        await db.execute(delete(TallerSolicitudPautaMecanico).where(
            TallerSolicitudPautaMecanico.pauta_id.in_(pauta_ids.values()),
        ))
        values = [{"pauta_id": pauta_ids[r["item_id"]], "mecanico_id": mecanico_id}
                  for r in respuestas for mecanico_id in r["mecanicos_ids"]]
        if values:
            await db.execute(insert(TallerSolicitudPautaMecanico), values)

    async def upsert_pauta_respuestas(
        self, db: AsyncSession, solicitud_id: int, respuestas: List[dict], mecanico_id: int, now: datetime
    ) -> None:
        """
        Upsert de respuestas y reemplazo de ejecutores dentro de la transacción del servicio.
        Usa ON CONFLICT DO UPDATE según el dialecto (PostgreSQL o SQLite).
        """
        if not respuestas:
            return

        respuestas = [dict(r, mecanicos_ids=sorted(r.get("mecanicos_ids") or [r.get("mecanico_id", mecanico_id)]))
                      for r in respuestas]

        values = [
            {
                "solicitud_id": solicitud_id,
                "item_id": r["item_id"],
                "estado": r["estado"],
                "observacion": r.get("observacion"),
                "mecanico_id": r["mecanicos_ids"][0],
                "fecha_registro": now,
            }
            for r in respuestas
        ]

        if db.bind and db.bind.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(TallerSolicitudPauta).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["solicitud_id", "item_id"],
                set_={
                    "estado": stmt.excluded.estado,
                    "observacion": stmt.excluded.observacion,
                    "mecanico_id": stmt.excluded.mecanico_id,
                    "fecha_registro": stmt.excluded.fecha_registro,
                },
            )
            await db.execute(stmt)
        elif db.bind and db.bind.dialect.name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert
            stmt = sqlite_insert(TallerSolicitudPauta).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["solicitud_id", "item_id"],
                set_={
                    "estado": stmt.excluded.estado,
                    "observacion": stmt.excluded.observacion,
                    "mecanico_id": stmt.excluded.mecanico_id,
                    "fecha_registro": stmt.excluded.fecha_registro,
                },
            )
            await db.execute(stmt)
        else:
            for val in values:
                existing = await db.execute(
                    select(TallerSolicitudPauta).where(
                        and_(
                            TallerSolicitudPauta.solicitud_id == solicitud_id,
                            TallerSolicitudPauta.item_id == val["item_id"],
                        )
                    )
                )
                obj = existing.scalar_one_or_none()
                if obj:
                    obj.estado = val["estado"]
                    obj.observacion = val["observacion"]
                    obj.mecanico_id = val["mecanico_id"]
                    obj.fecha_registro = val["fecha_registro"]
                else:
                    db.add(TallerSolicitudPauta(**val))
            await db.flush()

        await self.reemplazar_revisores(db, solicitud_id, respuestas)

    async def get_conteo_pauta_y_mecanico(
        self, db: AsyncSession, solicitud_id: int, mecanico_id: int
    ) -> tuple[int, int, Optional[str], bool]:
        """
        Retorna (total_pauta, respondidos_pauta, nombre_mecanico, solicitud_existe)
        en exactamente 1 sola consulta SQL nativa consolidada.
        """
        stmt = select(
            select(func.count(PautaTallerItem.id)).where(PautaTallerItem.is_active == True).scalar_subquery().label("total_pauta"),
            select(func.count(TallerSolicitudPauta.id)).where(TallerSolicitudPauta.solicitud_id == solicitud_id).scalar_subquery().label("respondidos_pauta"),
            select(Usuario.nombre).where(Usuario.id == mecanico_id).scalar_subquery().label("u_nombre"),
            select(Usuario.apellido).where(Usuario.id == mecanico_id).scalar_subquery().label("u_apellido"),
            select(TallerSolicitud.id).where(TallerSolicitud.id == solicitud_id).scalar_subquery().label("solicitud_id"),
        )
        res = await db.execute(stmt)
        row = res.first()
        if not row:
            return 0, 0, None, False
        total_p = row[0] or 0
        resp_p = row[1] or 0
        u_nom = row[2]
        u_ape = row[3]
        sol_id = row[4]
        mec_nombre = f"{u_nom or ''} {u_ape or ''}".strip() or None
        sol_existe = sol_id is not None
        return total_p, resp_p, mec_nombre, sol_existe

    async def check_solicitud_exists(self, db: AsyncSession, solicitud_id: int) -> bool:
        """Verifica existencia de la solicitud mediante una consulta de id ligero."""
        stmt = select(TallerSolicitud.id).where(TallerSolicitud.id == solicitud_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none() is not None


pauta_repository = PautaRepository()
