import pytest
import jwt
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.config import settings
from app.modules.auth.repository.user_repository import user_repository
from app.modules.auth.dtos.usuario_dto import UsuarioCreateDTO


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


@pytest.mark.asyncio
async def test_user_repository_create_and_authenticate(db_session):
    """Prueba la creación de un usuario y la autenticación mediante user_repository."""
    user_in = UsuarioCreateDTO(
        nombre="Test",
        apellido="User",
        username="testuser",
        password="mysecretpassword",
        rol="MECANICO",
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
        rol="CONDUCTOR",
    )
    user = await user_repository.create(db_session, user_in)
    assert user.is_active is True

    desactivated = await user_repository.desactivar(db_session, user.id)
    assert desactivated is not None
    assert desactivated.is_active is False


@pytest.mark.asyncio
async def test_auth_service_deshabilitar_usuario(db_session):
    """Prueba el caso de uso deshabilitar_usuario en AuthService."""
    from app.modules.auth.services.auth_service import auth_service
    from app.core.exceptions import BusinessRuleException, NotFoundException

    user_in = UsuarioCreateDTO(
        nombre="Servicio",
        apellido="Test",
        username="user_service_test",
        password="password123",
        rol="MECANICO",
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
