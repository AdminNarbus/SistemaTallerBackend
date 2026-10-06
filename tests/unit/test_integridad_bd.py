from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.models import Base
from app.modules.formularios.dtos.neumaticos_dto import ReporteNeumaticoCreateDTO
from app.modules.taller.utils import calcular_horas_en_taller


@pytest.mark.parametrize('ruedas', [[], [1, 2], None, '[1,2]', '[', [True], [' '], [-1]])
def test_rechaza_neumaticos_invalidos(ruedas):
    with pytest.raises(ValidationError):
        ReporteNeumaticoCreateDTO(ruedas=ruedas)


@pytest.mark.parametrize('ruedas', ['Rueda 4', '"Rueda 4"', '["Rueda 4"]', ['Rueda 4']])
def test_normaliza_una_rueda_y_marca_opcional(ruedas):
    dto = ReporteNeumaticoCreateDTO(ruedas=ruedas, marca_fuego='  MF-001  ')
    assert dto.ruedas == ['Rueda 4']
    assert dto.marca_fuego == 'MF-001'
    assert ReporteNeumaticoCreateDTO(ruedas=ruedas).marca_fuego is None


def test_calcula_horas_con_distintos_offsets():
    ingreso = datetime(2026, 9, 29, 10, tzinfo=timezone(timedelta(hours=-3)))
    salida = datetime(2026, 9, 29, 15, tzinfo=timezone.utc)
    assert calcular_horas_en_taller(ingreso, salida) == 2.0


def test_fk_compuesta_impide_mezclar_ots_y_protege_historial():
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(text('PRAGMA foreign_keys=ON'))
        Base.metadata.create_all(connection)
        connection.execute(text("INSERT INTO roles(id,nombre) VALUES (1,'MECANICO')"))
        connection.execute(text("INSERT INTO usuarios(id,username,password_hash,rol_id) VALUES (1,'test','test',1)"))
        connection.execute(text("INSERT INTO taller_solicitudes(id,n_bus) VALUES (1,'OT1'),(2,'OT2')"))
        connection.execute(text("INSERT INTO taller_solicitud_detalles(id,solicitud_id) VALUES (1,1)"))
        connection.execute(text("INSERT INTO taller_solicitud_comentarios(id,solicitud_id,usuario_id,comentario) VALUES (1,1,1,'Historial')"))
        for statement in [
            "INSERT INTO taller_asignacion_fallas(solicitud_id,detalle_id,mecanico_id) VALUES (2,1,1)",
            "INSERT INTO taller_solicitud_evidencias(solicitud_id,detalle_id,url) VALUES (2,1,'test')",
            "INSERT INTO taller_solicitud_evidencias(solicitud_id,comentario_id,url) VALUES (2,1,'test')",
            'DELETE FROM usuarios WHERE id=1',
            'DELETE FROM taller_solicitudes WHERE id=1',
        ]:
            with connection.begin_nested():
                with pytest.raises(IntegrityError):
                    connection.execute(text(statement))
    engine.dispose()


@pytest.mark.asyncio
async def test_seed_pauta_conserva_respuestas_con_ids_mayores_a_diez(db_session, seed_test_data):
    from sqlalchemy import select
    from app.core.seed import _seed_pauta_preventiva
    from app.modules.taller.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta
    from app.modules.taller.models.taller_solicitud import TallerSolicitud

    ot = TallerSolicitud(n_bus='PAUTA-ID-HISTORICO')
    item = PautaTallerItem(id=500, categoria='Motor', item='Revisión', orden=1)
    anterior = PautaTallerItem(id=501, categoria='Motor', item='Anterior', orden=1, is_active=False)
    db_session.add_all([ot, item, anterior])
    await db_session.flush()
    respuesta = TallerSolicitudPauta(solicitud_id=ot.id, item_id=500, estado='OK')
    db_session.add(respuesta)
    await db_session.commit()

    await _seed_pauta_preventiva(db_session)

    assert await db_session.scalar(select(TallerSolicitudPauta.id).where(TallerSolicitudPauta.item_id == 500)) == respuesta.id
    activos = (await db_session.scalars(select(PautaTallerItem).where(PautaTallerItem.is_active.is_(True)))).all()
    assert len(activos) == 10
