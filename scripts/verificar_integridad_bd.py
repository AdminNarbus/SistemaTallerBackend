"""Auditoría SELECT previa al despliegue; nunca cambia registros ni el esquema."""
import importlib.util
import logging
from pathlib import Path

from sqlalchemy import CheckConstraint, create_engine, inspect, text
from app.core.config import settings

logger = logging.getLogger(__name__)


def auditar_historial_estados(connection):
    if not inspect(connection).has_table('taller_solicitud_estado_eventos'):
        return []  # Compatible con el preflight de entornos aún anteriores a 024.
    from app.modules.taller.models.taller_solicitud_estado_evento import TallerSolicitudEstadoEvento
    findings = []
    for constraint in TallerSolicitudEstadoEvento.__table__.constraints:
        if isinstance(constraint, CheckConstraint):
            count = connection.scalar(text(
                f'SELECT count(*) FROM taller_solicitud_estado_eventos WHERE ({constraint.sqltext}) IS FALSE'
            ))
            if count:
                findings.append((constraint.name, count))
    rules = {
        'estado_evento_ot_inexistente': 'SELECT count(*) FROM taller_solicitud_estado_eventos e LEFT JOIN taller_solicitudes s ON s.id=e.solicitud_id WHERE s.id IS NULL',
        'estado_evento_actor_inexistente': 'SELECT count(*) FROM taller_solicitud_estado_eventos e LEFT JOIN usuarios u ON u.id=e.usuario_actor_id WHERE e.usuario_actor_id IS NOT NULL AND u.id IS NULL',
        'estado_evento_comentario_ot': 'SELECT count(*) FROM taller_solicitud_estado_eventos e LEFT JOIN taller_solicitud_comentarios c ON c.id=e.comentario_id AND c.solicitud_id=e.solicitud_id WHERE e.comentario_id IS NOT NULL AND c.id IS NULL',
        'estado_evento_comentario_duplicado': 'SELECT count(*) FROM (SELECT comentario_id FROM taller_solicitud_estado_eventos WHERE comentario_id IS NOT NULL GROUP BY comentario_id HAVING count(*)>1) d',
        'estado_evento_proteccion_ausente': "SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='taller_solicitud_estado_eventos'::regclass AND tgname='tr_estado_eventos_inmutables' AND tgenabled IN ('O','A')) THEN 0 ELSE 1 END",
    }
    for name, query in rules.items():
        count = connection.scalar(text(query))
        if count:
            findings.append((name, count))
    return findings


def main() -> None:
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/022_integridad_bd.py'
    spec = importlib.util.spec_from_file_location('integridad_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(settings.sync_database_url)
    with engine.connect() as connection:
        connection.exec_driver_sql('SET TRANSACTION READ ONLY')
        findings = migration.audit(connection)
        findings.extend(auditar_historial_estados(connection))
    engine.dispose()
    for rule, count in findings:
        logger.error('Regla incompatible: %s | registros/grupos=%s', rule, count)
    if findings:
        raise SystemExit(1)
    logger.info('Auditoría de integridad aprobada; sin datos incompatibles')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
