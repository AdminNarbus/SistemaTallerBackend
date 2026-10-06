"""Consolidar OTs activas duplicadas y proteger la unicidad por bus.

Revision ID: 021_consolidar_ots_activas
Revises: 020_trazabilidad_fallas
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "021_consolidar_ots_activas"
down_revision: Union[str, None] = "020a_archivo_consolidacion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # asyncpg prepara cada op.execute; por eso cada instrucción debe viajar
        # separada aunque Alembic mantenga todo el upgrade en una transacción.
        statements = (
            """
            UPDATE taller_solicitudes s
            SET bus_id = b.id
            FROM buses b
            WHERE s.bus_id IS NULL
              AND lower(trim(s.n_bus)) = lower(trim(b.n_bus))
            """,
            """

            CREATE TEMP TABLE ot_consolidacion_map ON COMMIT DROP AS
            WITH activas AS (
                SELECT s.id,
                       first_value(s.id) OVER (
                           PARTITION BY COALESCE('B:' || s.bus_id::text, 'N:' || lower(trim(s.n_bus)))
                           ORDER BY s.fecha_creacion ASC, s.id ASC
                       ) AS destino_id,
                       row_number() OVER (
                           PARTITION BY COALESCE('B:' || s.bus_id::text, 'N:' || lower(trim(s.n_bus)))
                           ORDER BY s.fecha_creacion ASC, s.id ASC
                       ) AS orden
                FROM taller_solicitudes s
                WHERE s.estado <> 'FINALIZADO'
            )
            SELECT id AS origen_id, destino_id
            FROM activas WHERE orden > 1
            """,
            """

            UPDATE taller_asignacion_fallas a
            SET solicitud_id = m.destino_id
            FROM ot_consolidacion_map m
            WHERE a.solicitud_id = m.origen_id
            """,
            """

            UPDATE taller_solicitud_detalles d
            SET solicitud_id = m.destino_id
            FROM ot_consolidacion_map m
            WHERE d.solicitud_id = m.origen_id
            """,
            """

            UPDATE taller_solicitud_evidencias e
            SET solicitud_id = m.destino_id
            FROM ot_consolidacion_map m
            WHERE e.solicitud_id = m.origen_id
            """,
            """

            UPDATE taller_solicitud_comentarios c
            SET solicitud_id = m.destino_id
            FROM ot_consolidacion_map m
            WHERE c.solicitud_id = m.origen_id
            """,
            """

            UPDATE taller_solicitud_mecanicos sm
            SET solicitud_id = m.destino_id
            FROM ot_consolidacion_map m
            WHERE sm.solicitud_id = m.origen_id
            """,
            """

            WITH pautas_ranked AS (
                SELECT p.id, COALESCE(m.destino_id, p.solicitud_id) AS destino_id,
                       row_number() OVER (
                           PARTITION BY COALESCE(m.destino_id, p.solicitud_id), p.item_id
                           ORDER BY p.fecha_registro DESC, p.id DESC
                       ) AS orden
                FROM taller_solicitud_pauta p
                LEFT JOIN ot_consolidacion_map m ON m.origen_id = p.solicitud_id
            )
            DELETE FROM taller_solicitud_pauta p
            USING pautas_ranked r
            WHERE p.id = r.id AND r.orden > 1
            """,
            """

            UPDATE taller_solicitud_pauta p
            SET solicitud_id = m.destino_id
            FROM ot_consolidacion_map m
            WHERE p.solicitud_id = m.origen_id
            """,
            """

            UPDATE taller_solicitud_estadias es
            SET solicitud_id = m.destino_id
            FROM ot_consolidacion_map m
            WHERE es.solicitud_id = m.origen_id
            """,
            """

            WITH ordenadas AS (
                SELECT es.id,
                       row_number() OVER (
                           PARTITION BY es.solicitud_id
                           ORDER BY es.fecha_ingreso ASC, es.id ASC
                       ) AS nueva_visita
                FROM taller_solicitud_estadias es
                WHERE es.solicitud_id IN (SELECT DISTINCT destino_id FROM ot_consolidacion_map)
            )
            UPDATE taller_solicitud_estadias es
            SET numero_visita = o.nueva_visita
            FROM ordenadas o
            WHERE es.id = o.id
            """,
            """

            UPDATE taller_solicitudes destino
            SET fecha_actualizacion = fuentes.ultima_actualizacion,
                estado = CASE WHEN fuentes.tiene_asignacion_activa THEN 'EN_REPARACION' ELSE destino.estado END
            FROM (
                SELECT m.destino_id,
                       max(origen.fecha_actualizacion) AS ultima_actualizacion,
                       bool_or(a.is_activo) AS tiene_asignacion_activa
                FROM ot_consolidacion_map m
                JOIN taller_solicitudes origen ON origen.id = m.origen_id
                LEFT JOIN taller_asignacion_fallas a ON a.solicitud_id = m.destino_id
                GROUP BY m.destino_id
            ) fuentes
            WHERE destino.id = fuentes.destino_id
            """,
            """

            UPDATE taller_solicitudes origen
            SET estado = 'FINALIZADO',
                fecha_cierre = now(),
                motivo_cierre_parcial = 'Consolidada automáticamente en OT #' || m.destino_id
            FROM ot_consolidacion_map m
            WHERE origen.id = m.origen_id
            """,
        )
        for statement in statements:
            op.execute(statement)

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_taller_solicitudes_bus_activa "
        "ON taller_solicitudes (bus_id) "
        "WHERE bus_id IS NOT NULL AND estado <> 'FINALIZADO'"
    )
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_taller_solicitudes_n_bus_activa_sin_bus_id "
            "ON taller_solicitudes ((lower(trim(n_bus)))) "
            "WHERE bus_id IS NULL AND estado <> 'FINALIZADO'"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_taller_solicitudes_n_bus_activa_sin_bus_id")
    op.execute("DROP INDEX IF EXISTS uq_taller_solicitudes_bus_activa")
