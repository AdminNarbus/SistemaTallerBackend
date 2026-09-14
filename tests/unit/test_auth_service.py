from unittest.mock import AsyncMock, patch
import pytest
import jwt
from app.core.exceptions import (
    AuthenticationException,
    BusinessRuleException,
    ConflictException,
    NotFoundException,
)
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings
from app.modules.auth.constants import RolUsuario
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.repository.user_repository import user_repository
from app.modules.auth.services.auth_service import auth_service
from app.modules.auth.dtos.usuario_dto import UsuarioCreateDTO, UsuarioLoginDTO


def test_password_hashing():
    """Prueba que el hash bcrypt encripte correctamente y valide la clave."""
    raw_password = "SecretPassword123!"
    hashed = get_password_hash(raw_password)

    assert hashed != raw_password
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_token_generation_and_decoding():
    """Prueba la generación y decodificación de tokens JWT de acceso."""
    user_id = 99
    token = create_access_token(subject=user_id)

    assert isinstance(token, str)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload.get("sub") == str(user_id)
    assert "exp" in payload


# =====================================================================
# PRUEBAS UNITARIAS PURAS CON MOCKS (AAA) - AUTH SERVICE
# =====================================================================

@pytest.mark.asyncio
async def test_auth_service_login_exitoso():
    """Prueba login exitoso retornando TokenDTO con usuario autenticado."""
    # Arrange
    mock_db = AsyncMock()
    login_dto = UsuarioLoginDTO(username="juan", password="password123")
    hashed_pwd = get_password_hash("password123")
    mock_rol = Rol(id=3, nombre="CONDUCTOR", descripcion="Conductor")
    mock_usuario = Usuario(
        id=1,
        username="juan",
        password_hash=hashed_pwd,
        rol_id=3,
        is_active=True,
    )
    mock_usuario.rol_rel = mock_rol

    with patch("app.modules.auth.services.auth_service.user_repository.get_by_username", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_usuario

        # Act
        token_dto = await auth_service.login(mock_db, login_dto)

        # Assert
        assert token_dto.access_token is not None
        assert token_dto.token_type == "bearer"
        assert token_dto.user.username == "juan"
        assert token_dto.user.rol == "CONDUCTOR"
        mock_get.assert_awaited_once_with(mock_db, username="juan")


@pytest.mark.asyncio
async def test_auth_service_login_credenciales_invalidas():
    """Prueba rechazo con AuthenticationException ante contraseña incorrecta."""
    # Arrange
    mock_db = AsyncMock()
    login_dto = UsuarioLoginDTO(username="juan", password="wrongpassword")
    hashed_pwd = get_password_hash("password123")
    mock_rol = Rol(id=3, nombre="CONDUCTOR")
    mock_usuario = Usuario(
        id=1,
        username="juan",
        password_hash=hashed_pwd,
        rol_id=3,
        is_active=True,
    )
    mock_usuario.rol_rel = mock_rol

    with patch("app.modules.auth.services.auth_service.user_repository.get_by_username", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_usuario

        # Act & Assert
        with pytest.raises(AuthenticationException) as exc_info:
            await auth_service.login(mock_db, login_dto)
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_service_login_usuario_inactivo():
    """Prueba rechazo con BusinessRuleException cuando el usuario está desactivado."""
    # Arrange
    mock_db = AsyncMock()
    login_dto = UsuarioLoginDTO(username="inactivo", password="password123")
    hashed_pwd = get_password_hash("password123")
    mock_rol = Rol(id=3, nombre="CONDUCTOR")
    mock_usuario = Usuario(
        id=2,
        username="inactivo",
        password_hash=hashed_pwd,
        rol_id=3,
        is_active=False,
    )
    mock_usuario.rol_rel = mock_rol

    with patch("app.modules.auth.services.auth_service.user_repository.get_by_username", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_usuario

        # Act & Assert
        with pytest.raises(BusinessRuleException) as exc_info:
            await auth_service.login(mock_db, login_dto)
        assert "inactivo" in exc_info.value.message


@pytest.mark.asyncio
async def test_auth_service_register_rol_invalido():
    """Prueba rechazo si el rol solicitado no pertenece a los roles permitidos."""
    # Arrange
    mock_db = AsyncMock()
    # Construir un DTO con rol no permitido usando model_construct para saltar validación Pydantic
    dto = UsuarioCreateDTO.model_construct(
        username="pedro",
        password="password123",
        rol="ROL_HACKER",
    )

    with patch("app.modules.auth.services.auth_service.user_repository.get_by_username", new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = None

        # Act & Assert
        with pytest.raises(BusinessRuleException) as exc_info:
            await auth_service.register(mock_db, dto)
        assert "no es válido" in exc_info.value.message


@pytest.mark.asyncio
async def test_auth_service_register_duplicado():
    """Prueba rechazo con ConflictException al intentar registrar un username existente."""
    # Arrange
    mock_db = AsyncMock()
    dto = UsuarioCreateDTO(
        username="existente",
        password="password123",
        rol=RolUsuario.CONDUCTOR,
    )
    mock_usuario = Usuario(id=1, username="existente")

    with patch("app.modules.auth.services.auth_service.user_repository.get_by_username", new_callable=AsyncMock) as mock_get_user:
        mock_get_user.return_value = mock_usuario

        # Act & Assert
        with pytest.raises(ConflictException) as exc_info:
            await auth_service.register(mock_db, dto)
        assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_auth_service_buscar_mecanicos_paginado():
    """Prueba que buscar_mecanicos invoque el repositorio con parámetros de paginación."""
    # Arrange
    mock_db = AsyncMock()
    mock_rol = Rol(id=4, nombre="MECANICO")
    m1 = Usuario(id=10, username="meca1", nombre="Mario", apellido="Bros", rol_id=4, is_active=True)
    m1.rol_rel = mock_rol
    m2 = Usuario(id=11, username="meca2", nombre="Luigi", apellido="Bros", rol_id=4, is_active=True)
    m2.rol_rel = mock_rol

    with patch("app.modules.auth.services.auth_service.user_repository.buscar_mecanicos", new_callable=AsyncMock) as mock_repo_buscar:
        mock_repo_buscar.return_value = [m1, m2]

        # Act
        resultados = await auth_service.buscar_mecanicos(
            mock_db, q="Bros", exclude_id=5, skip=10, limit=20
        )

        # Assert
        assert len(resultados) == 2
        assert resultados[0].username == "meca1"
        assert resultados[1].username == "meca2"
        mock_repo_buscar.assert_awaited_once_with(
            mock_db, q="Bros", exclude_id=5, skip=10, limit=20
        )


# =====================================================================
# PRUEBAS DE INTEGRACIÓN CON BASE DE DATOS (db_session)
# =====================================================================

@pytest.mark.asyncio
async def test_user_repository_create_and_authenticate(db_session):
    """Prueba la creación de un usuario y la autenticación mediante user_repository."""
    user_in = UsuarioCreateDTO(
        nombre="Test",
        apellido="User",
        username="testuser",
        password="mysecretpassword",
        rol=RolUsuario.MECANICO,
    )

    created_user = await user_repository.create(db_session, user_in)
    assert created_user.id is not None
    assert created_user.username == "testuser"
    assert created_user.is_active is True

    # Autenticación exitosa
    authenticated = await user_repository.authenticate(db_session, "testuser", "mysecretpassword")
    assert authenticated is not None
    assert authenticated.id == created_user.id

    # Autenticación fallida con clave errónea
    fail_pass = await user_repository.authenticate(db_session, "testuser", "wrongpass")
    assert fail_pass is None

    # Autenticación fallida con usuario inexistente
    fail_user = await user_repository.authenticate(db_session, "nonexistent", "mysecretpassword")
    assert fail_user is None


@pytest.mark.asyncio
async def test_user_repository_desactivar_soft_delete(db_session):
    """Prueba la funcionalidad de deshabilitar (soft-delete) un usuario."""
    user_in = UsuarioCreateDTO(
        nombre="ToDeactivate",
        apellido="User",
        username="user_deactivate",
        password="password123",
        rol=RolUsuario.CONDUCTOR,
    )
    user = await user_repository.create(db_session, user_in)
    assert user.is_active is True

    desactivated = await user_repository.desactivar(db_session, user.id)
    assert desactivated is not None
    assert desactivated.is_active is False


@pytest.mark.asyncio
async def test_auth_service_deshabilitar_usuario(db_session):
    """Prueba el caso de uso deshabilitar_usuario en AuthService."""
    user_in = UsuarioCreateDTO(
        nombre="Servicio",
        apellido="Test",
        username="user_service_test",
        password="password123",
        rol=RolUsuario.MECANICO,
    )
    user_dto = await auth_service.crear_usuario(db_session, user_in)
    assert user_dto.is_active is True

    # 1. Error al intentar deshabilitarse a sí mismo
    with pytest.raises(BusinessRuleException) as exc_info:
        await auth_service.deshabilitar_usuario(db_session, usuario_id=user_dto.id, current_user_id=user_dto.id)
    assert exc_info.value.status_code == 400

    # 2. Deshabilitar por otro usuario (ej: admin con id=999)
    res_dto = await auth_service.deshabilitar_usuario(db_session, usuario_id=user_dto.id, current_user_id=999)
    assert res_dto.id == user_dto.id
    assert res_dto.is_active is False

    # 3. Error con usuario inexistente
    with pytest.raises(NotFoundException):
        await auth_service.deshabilitar_usuario(db_session, usuario_id=88888, current_user_id=999)
