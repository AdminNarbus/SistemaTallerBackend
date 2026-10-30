from datetime import datetime, timedelta, timezone

from app.modules.taller.dtos.averias_dto import AsignacionFallaDTO, SolicitudDetalleDTO
from app.modules.taller.dtos.bitacora_dto import SolicitudComentarioDTO
from app.modules.taller.dtos.solicitud_dto import SolicitudDTO
from app.modules.taller.services.avances_falla_mapper import normalizar_avances_fallas


FECHA = datetime(2026, 10, 28, 13, 27, tzinfo=timezone.utc)


def asignacion(identificador, mecanico, fecha=FECHA):
    return AsignacionFallaDTO(
        id=identificador, solicitud_id=7, detalle_id=20, mecanico_id=mecanico,
        origen="AUTOASIGNACION", is_activo=False, fecha_desasignacion=fecha,
        resuelto_en_esta_asignacion=False, comentario="Falta rotor corto",
    )


def mensaje(identificador, fecha=FECHA):
    return SolicitudComentarioDTO(
        id=identificador, solicitud_id=7, usuario_id=145, usuario_nombre="Luis Linares",
        tipo="ENTREGA_TURNO", comentario="Avance del equipo. Falta rotor corto", fecha_registro=fecha,
    )


def ficha(asignaciones, comentarios):
    detalle = SolicitudDetalleDTO(
        id=20, solicitud_id=7, resuelto=False, fecha_creacion=FECHA,
        historial_asignaciones=asignaciones,
    )
    return SolicitudDTO(id=7, n_bus="1", fecha_creacion=FECHA, detalles=[detalle], comentarios=comentarios)


def test_un_avance_por_falla_con_autor_fecha_e_id_originales():
    # Arrange: Juan y Luis tienen copias del cierre ejecutado por Luis.
    solicitud = ficha([asignacion(1, 146), asignacion(2, 145)], [mensaje(575)])
    # Act
    resultado = normalizar_avances_fallas(solicitud).detalles[0]
    # Assert: el cliente recibe un mensaje y referencias, no notas repetidas.
    assert [c.id for c in resultado.historial_avances] == [575]
    assert resultado.historial_avances[0].usuario_id == 145
    assert resultado.historial_avances[0].fecha_registro == FECHA
    assert all(a.comentario is None and a.comentario_avance_id == 575 for a in resultado.historial_asignaciones)


def test_notas_iguales_en_turnos_distintos_no_se_fusionan():
    manana = FECHA + timedelta(days=1)
    solicitud = ficha([asignacion(1, 146), asignacion(2, 146, manana)], [mensaje(575), mensaje(600, manana)])
    resultado = normalizar_avances_fallas(solicitud).detalles[0]
    assert [c.id for c in resultado.historial_avances] == [575, 600]


def test_nota_sin_mensaje_global_o_con_coincidencia_ambigua_se_conserva():
    for comentarios in ([], [mensaje(575), mensaje(600)]):
        solicitud = ficha([asignacion(1, 146)], comentarios)
        resultado = normalizar_avances_fallas(solicitud).detalles[0]
        assert resultado.historial_avances == []
        assert resultado.historial_asignaciones[0].comentario == "Falta rotor corto"


def test_normalizacion_es_idempotente_y_admite_fechas_sqlite_sin_zona():
    solicitud = ficha([asignacion(1, 146, FECHA.replace(tzinfo=None))], [mensaje(575)])
    normalizar_avances_fallas(solicitud)
    normalizar_avances_fallas(solicitud)
    assert len(solicitud.detalles[0].historial_avances) == 1
