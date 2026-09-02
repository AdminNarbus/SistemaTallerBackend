import logging
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

async def apply_db_patches():
    """Aplica parches de esquema a tablas preexistentes en PostgreSQL para asegurar compatibilidad."""
    patches = [
        "ALTER TABLE buses ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS nombre VARCHAR(100);",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS apellido VARCHAR(100);",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS rol_id INTEGER REFERENCES roles(id) ON DELETE RESTRICT;",
        "ALTER TABLE taller_solicitudes ADD COLUMN IF NOT EXISTS usuario_creador_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL;",
        "ALTER TABLE taller_solicitudes ADD COLUMN IF NOT EXISTS mecanico_cierre_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL;",
        "ALTER TABLE taller_solicitudes ADD COLUMN IF NOT EXISTS descripcion_general TEXT;",
        "ALTER TABLE taller_solicitudes ADD COLUMN IF NOT EXISTS fecha_cierre TIMESTAMPTZ;",
        "ALTER TABLE taller_solicitudes ADD COLUMN IF NOT EXISTS bus_id INTEGER REFERENCES buses(id) ON DELETE SET NULL;",
        "ALTER TABLE reportes_neumaticos ADD COLUMN IF NOT EXISTS bus_id INTEGER REFERENCES buses(id) ON DELETE SET NULL;",
        "ALTER TABLE buses ADD COLUMN IF NOT EXISTS en_taller BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE taller_solicitudes ADD COLUMN IF NOT EXISTS motivo_incompleto_checklist TEXT;",
        "ALTER TABLE taller_solicitudes ADD COLUMN IF NOT EXISTS motivo_cierre_parcial TEXT;",
        "ALTER TABLE taller_solicitud_detalles ADD COLUMN IF NOT EXISTS falta_repuesto BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE taller_solicitud_detalles ADD COLUMN IF NOT EXISTS comentario_repuesto TEXT;",
        "ALTER TABLE taller_solicitud_mecanicos ADD COLUMN IF NOT EXISTS asignado_por_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL;",
        "ALTER TABLE taller_solicitud_mecanicos ADD COLUMN IF NOT EXISTS duracion_minutos INTEGER;",
        """
        CREATE TABLE IF NOT EXISTS taller_asignacion_fallas (
            id SERIAL PRIMARY KEY,
            solicitud_id INTEGER NOT NULL REFERENCES taller_solicitudes(id) ON DELETE CASCADE,
            detalle_id INTEGER NOT NULL REFERENCES taller_solicitud_detalles(id) ON DELETE CASCADE,
            mecanico_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            asignado_por_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
            origen VARCHAR(50) DEFAULT 'SUPERVISOR' NOT NULL,
            is_activo BOOLEAN DEFAULT TRUE NOT NULL,
            fecha_asignacion TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            fecha_desasignacion TIMESTAMPTZ,
            resuelto_en_esta_asignacion BOOLEAN DEFAULT FALSE NOT NULL,
            duracion_minutos INTEGER,
            comentario TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS pauta_taller_items (
            id SERIAL PRIMARY KEY,
            categoria VARCHAR(100) NOT NULL,
            item VARCHAR(255) NOT NULL,
            orden INTEGER DEFAULT 0 NOT NULL,
            is_active BOOLEAN DEFAULT TRUE NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS taller_solicitud_pauta (
            id SERIAL PRIMARY KEY,
            solicitud_id INTEGER NOT NULL REFERENCES taller_solicitudes(id) ON DELETE CASCADE,
            item_id INTEGER NOT NULL REFERENCES pauta_taller_items(id) ON DELETE CASCADE,
            estado VARCHAR(20) NOT NULL,
            observacion TEXT,
            mecanico_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
            fecha_registro TIMESTAMPTZ DEFAULT NOW() NOT NULL,
            CONSTRAINT uq_solicitud_pauta_item UNIQUE (solicitud_id, item_id)
        );
        """,
    ]

    async with AsyncSessionLocal() as db:
        for patch_sql in patches:
            try:
                await db.execute(text(patch_sql))
                await db.commit()
                logger.debug("[DB_PATCH] Parche aplicado | sql='%s'", patch_sql[:80])
            except Exception as e:
                await db.rollback()
                logger.warning("[DB_PATCH] Parche omitido (puede ser normal) | sql='%s...' | error=%s", patch_sql[:60], e)
