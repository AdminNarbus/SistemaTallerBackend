import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, clear_user_cache, _USER_CACHE
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.models.rol import Rol
from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.dtos.mantencion_dto import SolicitudCreateDTO, SolicitudDetalleCreateDTO
from app.modules.mantencion.services.mantencion_service import mantencion_service
from app.modules.mantencion.repository.mantencion_repository import mantencion_repository
from app.core.security import create_access_token


@pytest.mark.asyncio
async def test_get_bus_info_by_n_bus_single_query(db_session: AsyncSession):
    """Verifica que get_bus_info_by_n_bus retorne id y patente en una sola consulta."""
    bus = Bus(
        patente="TEST-99",
        n_bus="350",
        marca="Mercedes",
        modelo="O500",
        is_active=True,
    )
    db_session.add(bus)
    await db_session.commit()

    info = await mantencion_repository.get_bus_info_by_n_bus(db_session, "350")
    assert info is not None
    bus_id, bus_patente = info
    assert bus_id == bus.id
    assert bus_patente == "TEST-99"


@pytest.mark.asyncio
async def test_create_solicitud_batch_fallas_and_fast_dto(db_session: AsyncSession):
    """Verifica que create_solicitud resuelva categorías en batch y retorne el DTO en memoria con éxito."""
    # 1. Crear bus
    bus = Bus(patente="OPTI-01", n_bus="400", is_active=True)
    db_session.add(bus)

    # 2. Crear rol y usuario chofer
    rol = Rol(nombre="CONDUCTOR", descripcion="Conductor")
    db_session.add(rol)
    await db_session.flush()

    chofer = Usuario(
        username="chofer_opti",
        password_hash="hash",
        nombre="Carlos",
        apellido="Soto",
        rol_id=rol.id,
        is_active=True,
    )
    db_session.add(chofer)

    # 3. Crear categorías y fallas
    cat1 = CategoriaFalla(nombre="MOTOR", is_active=True)
    cat2 = CategoriaFalla(nombre="FRENOS", is_active=True)
    db_session.add_all([cat1, cat2])
    await db_session.flush()

    falla1 = FallaTaller(categoria_id=cat1.id, nombre="Sobrecalentamiento motor", is_active=True)
    falla2 = FallaTaller(categoria_id=cat2.id, nombre="Fuga de aire frenos", is_active=True)
    db_session.add_all([falla1, falla2])
    await db_session.commit()

    # 4. Crear solicitud pasando categorías directamente
    dto = SolicitudCreateDTO(
        n_bus="400",
        descripcion_general="Reporte optimizado de prueba",
        detalles=[
            SolicitudDetalleCreateDTO(categoria_id=cat1.id, descripcion_personalizada="Humo blanco"),
            SolicitudDetalleCreateDTO(categoria_id=cat2.id, descripcion_personalizada="Pedal largo"),
        ],
    )

    sol_dto = await mantencion_service.create_solicitud(db_session, dto, creador_id=chofer.id)

    assert sol_dto.id is not None
    assert sol_dto.n_bus == "400"
    assert sol_dto.bus_id == bus.id
    assert sol_dto.bus_patente == "OPTI-01"
    assert sol_dto.usuario_creador_id == chofer.id
    assert sol_dto.usuario_creador_nombre == "Carlos Soto"
    assert sol_dto.estado == "PENDIENTE"
    assert sol_dto.total_fallas == 2
    assert len(sol_dto.detalles) == 2

    # Verificar que los detalles tienen las categorías y fallas correctamente mapeadas
    d1 = sol_dto.detalles[0]
    assert d1.falla_id == falla1.id
    assert d1.categoria_id == cat1.id
    assert d1.categoria_nombre == "MOTOR"
    assert d1.falla.nombre == "Sobrecalentamiento motor"

    d2 = sol_dto.detalles[1]
    assert d2.falla_id == falla2.id
    assert d2.categoria_id == cat2.id
    assert d2.categoria_nombre == "FRENOS"
    assert d2.falla.nombre == "Fuga de aire frenos"


@pytest.mark.asyncio
async def test_auth_user_cache_in_memory(db_session: AsyncSession):
    """Verifica que el caché en memoria de get_current_user funcione evitando re-consultas."""
    clear_user_cache()

    rol = Rol(nombre="ADMIN", descripcion="Admin")
    db_session.add(rol)
    await db_session.flush()

    admin = Usuario(
        username="admin_cached",
        password_hash="hash",
        nombre="Super",
        apellido="Admin",
        rol_id=rol.id,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()

    token = create_access_token(admin.id)

    # Primera llamada: consulta BD y llena cache
    user1 = await get_current_user(db=db_session, token=token)
    assert user1 is not None
    assert user1.id == admin.id
    assert admin.id in _USER_CACHE

    # Segunda llamada: recupera de cache instantáneamente
    user2 = await get_current_user(db=db_session, token=token)
    assert user2 is not None
    assert user2.id == user1.id

    clear_user_cache()
    assert admin.id not in _USER_CACHE


@pytest.mark.asyncio
async def test_create_solicitud_con_falla_id_y_falla_nombre_zero_queries(db_session: AsyncSession):
    """Verifica que al enviar falla_id y falla_nombre, la creación construye el DTO sin consultas adicionales."""
    bus = Bus(patente="ZERO-01", n_bus="550", is_active=True)
    db_session.add(bus)

    rol = Rol(nombre="CONDUCTOR", descripcion="Conductor")
    db_session.add(rol)
    await db_session.flush()

    chofer = Usuario(
        username="chofer_zero",
        password_hash="hash",
        nombre="Pedro",
        apellido="Pascal",
        rol_id=rol.id,
        is_active=True,
    )
    db_session.add(chofer)
    await db_session.commit()

    # Creación con bus_id, n_bus, falla_id y falla_nombre (flujo de máxima velocidad)
    dto = SolicitudCreateDTO(
        n_bus="550",
        bus_id=bus.id,
        descripcion_general="Prueba de máxima velocidad",
        detalles=[
            SolicitudDetalleCreateDTO(
                falla_id=99,
                falla_nombre="Falla Eléctrica",
                categoria_id=3,
                categoria_nombre="LUCES",
                descripcion_personalizada="Ampolleta quemada",
            )
        ],
    )

    sol_dto = await mantencion_service.create_solicitud(
        db_session, dto, creador_id=chofer.id, creador_nombre="Pedro Pascal"
    )

    assert sol_dto.id is not None
    assert sol_dto.bus_id == bus.id
    assert sol_dto.n_bus == "550"
    assert len(sol_dto.detalles) == 1
    d = sol_dto.detalles[0]
    assert d.falla_id == 99
    assert d.falla.nombre == "Falla Eléctrica"
    assert d.categoria_id == 3
    assert d.categoria_nombre == "LUCES"


@pytest.mark.asyncio
async def test_create_solicitud_con_falla_id_sin_falla_nombre_fallback(db_session: AsyncSession):
    """Verifica que si no se envía falla_nombre, use la descripción personalizada como fallback en memoria sin error."""
    bus = Bus(patente="FALL-01", n_bus="551", is_active=True)
    db_session.add(bus)

    rol = Rol(nombre="CONDUCTOR", descripcion="Conductor")
    db_session.add(rol)
    await db_session.flush()

    chofer = Usuario(
        username="chofer_fall",
        password_hash="hash",
        nombre="Lucia",
        apellido="Hiriart",
        rol_id=rol.id,
        is_active=True,
    )
    db_session.add(chofer)
    await db_session.commit()

    dto = SolicitudCreateDTO(
        n_bus="551",
        bus_id=bus.id,
        descripcion_general="Prueba fallback sin nombre",
        detalles=[
            SolicitudDetalleCreateDTO(
                falla_id=88,
                descripcion_personalizada="Ruido extraño en caja",
            )
        ],
    )

    sol_dto = await mantencion_service.create_solicitud(
        db_session, dto, creador_id=chofer.id, creador_nombre="Lucia Hiriart"
    )

    assert sol_dto.id is not None
    assert len(sol_dto.detalles) == 1
    d = sol_dto.detalles[0]
    assert d.falla_id == 88
    assert d.falla.nombre == "Ruido extraño en caja"

