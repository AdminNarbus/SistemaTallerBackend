from sqlalchemy import text
from app.core.database import AsyncSessionLocal

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
            except Exception as e:
                await db.rollback()
                print(f"[DB PATCH NOTE] {patch_sql} -> {e}")
