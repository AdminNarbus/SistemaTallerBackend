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
