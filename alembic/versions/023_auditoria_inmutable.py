"""Proteger bitácora y snapshots; reconciliar telemetría desde estadías.

Revision ID: 023_auditoria_inmutable
Revises: 022_integridad_bd
"""
from alembic import op

revision = '023_auditoria_inmutable'
down_revision = '022_integridad_bd'
branch_labels = None
depends_on = None


FUNCTIONS = [
    '''CREATE FUNCTION narbus_proteger_historial() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'El historial de % es inmutable; registrar un nuevo evento', TG_TABLE_NAME
            USING ERRCODE = '23514';
    END $$''',
    '''CREATE FUNCTION narbus_snapshot_falla() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_OP = 'UPDATE' THEN
            IF NEW.falla_nombre_snapshot IS DISTINCT FROM OLD.falla_nombre_snapshot
               OR NEW.categoria_nombre_snapshot IS DISTINCT FROM OLD.categoria_nombre_snapshot THEN
                RAISE EXCEPTION 'Los nombres históricos de una falla son inmutables' USING ERRCODE='23514';
            END IF;
        ELSIF NEW.falla_id IS NOT NULL THEN
            SELECT f.nombre, c.nombre INTO NEW.falla_nombre_snapshot, NEW.categoria_nombre_snapshot
            FROM fallas_taller f JOIN categorias_falla c ON c.id=f.categoria_id
            WHERE f.id=NEW.falla_id;
        END IF;
        RETURN NEW;
    END $$''',
    '''CREATE FUNCTION narbus_calcular_estadia() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        PERFORM 1 FROM taller_solicitudes WHERE id=NEW.solicitud_id FOR UPDATE;
        NEW.horas_estadia := CASE WHEN NEW.fecha_salida IS NULL THEN NULL
            ELSE round((extract(epoch FROM (NEW.fecha_salida - NEW.fecha_ingreso))/3600)::numeric, 1) END;
        RETURN NEW;
    END $$''',
    '''CREATE FUNCTION narbus_actualizar_telemetria() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        UPDATE taller_solicitudes s SET horas_taller_acumuladas=(
            SELECT COALESCE(sum(e.horas_estadia),0) FROM taller_solicitud_estadias e
            WHERE e.solicitud_id=s.id AND e.fecha_salida IS NOT NULL
        ) WHERE s.id=NEW.solicitud_id;
        UPDATE buses b SET en_taller=EXISTS (
            SELECT 1 FROM taller_solicitud_estadias e JOIN taller_solicitudes s ON s.id=e.solicitud_id
            WHERE s.bus_id=b.id AND s.estado <> 'FINALIZADO' AND e.fecha_salida IS NULL
        ) WHERE b.id=(SELECT bus_id FROM taller_solicitudes WHERE id=NEW.solicitud_id);
        RETURN NEW;
    END $$''',
]

TRIGGERS = [
    ('tr_bitacora_inmutable', 'taller_solicitud_comentarios', 'BEFORE UPDATE OR DELETE', 'narbus_proteger_historial'),
    ('tr_eventos_inmutables', 'taller_falla_eventos', 'BEFORE UPDATE OR DELETE', 'narbus_proteger_historial'),
    ('tr_participantes_inmutables', 'taller_falla_evento_mecanicos', 'BEFORE UPDATE OR DELETE', 'narbus_proteger_historial'),
    ('tr_snapshot_falla', 'taller_solicitud_detalles', 'BEFORE INSERT OR UPDATE', 'narbus_snapshot_falla'),
    ('tr_calcular_estadia', 'taller_solicitud_estadias', 'BEFORE INSERT OR UPDATE', 'narbus_calcular_estadia'),
    ('tr_telemetria_estadia', 'taller_solicitud_estadias', 'AFTER INSERT OR UPDATE', 'narbus_actualizar_telemetria'),
    ('tr_estadias_no_borrar', 'taller_solicitud_estadias', 'BEFORE DELETE', 'narbus_proteger_historial'),
]


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    # Rebuild deterministic caches before installing protection; no business dates are invented.
    op.execute('''UPDATE taller_solicitud_estadias SET horas_estadia=CASE WHEN fecha_salida IS NULL THEN NULL
        ELSE round((extract(epoch FROM (fecha_salida-fecha_ingreso))/3600)::numeric,1) END''')
    op.execute('''UPDATE taller_solicitudes s SET horas_taller_acumuladas=(
        SELECT COALESCE(sum(e.horas_estadia),0) FROM taller_solicitud_estadias e
        WHERE e.solicitud_id=s.id AND e.fecha_salida IS NOT NULL)
        WHERE EXISTS (SELECT 1 FROM taller_solicitud_estadias e WHERE e.solicitud_id=s.id)''')
    op.execute('''UPDATE buses b SET en_taller=EXISTS (
        SELECT 1 FROM taller_solicitud_estadias e JOIN taller_solicitudes s ON s.id=e.solicitud_id
        WHERE s.bus_id=b.id AND s.estado <> 'FINALIZADO' AND e.fecha_salida IS NULL)
        WHERE EXISTS (SELECT 1 FROM taller_solicitudes s WHERE s.bus_id=b.id AND s.estado <> 'FINALIZADO')''')
    for statement in FUNCTIONS:
        op.execute(statement)
    for name, table, timing, function in TRIGGERS:
        op.execute(f'CREATE TRIGGER {name} {timing} ON {table} FOR EACH ROW EXECUTE FUNCTION {function}()')


def downgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    for name, table, _, _ in reversed(TRIGGERS):
        op.execute(f'DROP TRIGGER {name} ON {table}')
    for function in ('narbus_actualizar_telemetria', 'narbus_calcular_estadia', 'narbus_snapshot_falla', 'narbus_proteger_historial'):
        op.execute(f'DROP FUNCTION {function}()')
