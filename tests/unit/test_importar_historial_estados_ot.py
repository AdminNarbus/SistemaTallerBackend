from datetime import datetime, timezone

import pytest

from scripts.importar_historial_estados_ot import interpretar_comentario


def comentario(tipo, texto):
    return dict(id=10, solicitud_id=2, usuario_id=4, tipo=tipo, comentario=texto,
                fecha_registro=datetime(2026, 10, 1, tzinfo=timezone.utc))


def test_cambio_explicito_conserva_datos():
    row = comentario('CAMBIO_ESTADO', 'Supervisora Ana Pérez cambió el estado de FINALIZADO a PENDIENTE. Motivo: Revisar nuevamente')
    evento = interpretar_comentario(row)
    assert evento['estado_anterior'] == 'FINALIZADO'
    assert evento['estado_nuevo'] == 'PENDIENTE'
    assert evento['actor_nombre_snapshot'] == 'Ana Pérez'
    assert evento['motivo'] == 'Revisar nuevamente'
    assert evento['fecha_evento'] == row['fecha_registro']
    assert evento['comentario_id'] == 10


@pytest.mark.parametrize('texto', [
    'Pedro finalizó los trabajos de la OT y liberó el bus para operaciones.',
    'Pedro finalizó los trabajos de la OT (el bus permanece en taller). Comentario de cierre: Prueba. Motivo cierre parcial: Pendiente.',
])
def test_cierre_ambiguo_no_prueba_finalizacion(texto):
    evento = interpretar_comentario(comentario('CIERRE', texto))
    assert evento['tipo_evento'] == 'CIERRE_HISTORICO'
    assert evento['estado_anterior'] is None and evento['estado_nuevo'] is None


@pytest.mark.parametrize('tipo,texto', [
    ('GENERAL', 'Supervisora Ana cambió el estado de FINALIZADO a PENDIENTE.'),
    ('CAMBIO_ESTADO', 'Supervisora Ana cambió el estado de FINALIZADO a DESCONOCIDO.'),
    ('CAMBIO_ESTADO', 'Supervisora Ana cambió el estado de PENDIENTE a PENDIENTE.'),
    ('CIERRE', 'Creo que finalizaron ayer'),
    ('CAMBIO_ESTADO', 'Se cambió FINALIZADO a PENDIENTE'),
])
def test_no_inventa_transiciones(tipo, texto):
    assert interpretar_comentario(comentario(tipo, texto)) is None
