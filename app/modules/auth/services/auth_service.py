import logging
from typing import List, Optional
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationException, BusinessRuleException, ConflictException, NotFoundException
from app.core.security import create_access_token
from app.modules.auth.dtos import (
    TokenDTO,
    UsuarioCreateDTO,
    UsuarioLoginDTO,
    UsuarioResponseDTO,
)
from app.modules.auth.repository.user_repository import user_repository

logger = logging.getLogger(__name__)


class AuthService:
    """
    Capa de servicio de negocio para autenticación, generación de tokens y gestión de cuentas de usuario.
    """

    async def login(self, db: AsyncSession, login_data: UsuarioLoginDTO) -> TokenDTO:
        logger.info("[AUTH] Intento de login JSON | username='%s'", login_data.username)
        user = await user_repository.authenticate(
            db, username=login_data.username, password=login_data.password
        )
        if not user:
            raise AuthenticationException("Usuario o contraseña incorrectos.")
        if not user.is_active:
            raise BusinessRuleException("El usuario se encuentra inactivo.")

        access_token = create_access_token(subject=user.id)
        logger.info("[AUTH] Token JWT generado | id=%s | username='%s'", user.id, user.username)

        return TokenDTO(
            access_token=access_token,
            token_type="bearer",
            user=UsuarioResponseDTO.model_validate(user),
        )

    async def login_access_token(
        self, db: AsyncSession, form_data: OAuth2PasswordRequestForm
    ) -> TokenDTO:
        logger.info("[AUTH] Intento de login OAuth2 form | username='%s'", form_data.username)
        user = await user_repository.authenticate(
            db, username=form_data.username, password=form_data.password
        )
        if not user:
            raise AuthenticationException("Usuario o contraseña incorrectos.")
        if not user.is_active:
            raise BusinessRuleException("El usuario se encuentra inactivo.")

        access_token = create_access_token(subject=user.id)
        logger.info("[AUTH] Token JWT generado (OAuth2) | id=%s | username='%s'", user.id, user.username)

        return TokenDTO(
            access_token=access_token,
            token_type="bearer",
            user=UsuarioResponseDTO.model_validate(user),
        )

    async def register(
        self, db: AsyncSession, usuario_in: UsuarioCreateDTO
    ) -> TokenDTO:
        logger.info("[AUTH] Solicitud de registro | username='%s' | rol='%s'", usuario_in.username, usuario_in.rol)
        user_existente = await user_repository.get_by_username(
            db, username=usuario_in.username
        )
        if user_existente:
            raise ConflictException("El nombre de usuario ya está registrado en el sistema.")

        nuevo_usuario = await user_repository.create(db, usuario_in=usuario_in)
        access_token = create_access_token(subject=nuevo_usuario.id)
        logger.info("[AUTH] Registro exitoso | id=%s | username='%s'", nuevo_usuario.id, nuevo_usuario.username)

        return TokenDTO(
            access_token=access_token,
            token_type="bearer",
            user=UsuarioResponseDTO.model_validate(nuevo_usuario),
        )

    async def crear_usuario(
        self, db: AsyncSession, usuario_in: UsuarioCreateDTO
    ) -> UsuarioResponseDTO:
        logger.info("[AUTH] Creación administrativa de usuario | username='%s' | rol='%s'", usuario_in.username, usuario_in.rol)
        user_existente = await user_repository.get_by_username(
            db, username=usuario_in.username
        )
        if user_existente:
            raise ConflictException("El nombre de usuario ya está registrado en el sistema.")

        nuevo_usuario = await user_repository.create(db, usuario_in=usuario_in)
        return UsuarioResponseDTO.model_validate(nuevo_usuario)

    async def listar_usuarios(
        self, db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[UsuarioResponseDTO]:
        usuarios = await user_repository.get_all(db, skip=skip, limit=limit)
        return [UsuarioResponseDTO.model_validate(u) for u in usuarios]

    async def buscar_mecanicos(
        self, db: AsyncSession, q: Optional[str] = None, exclude_id: Optional[int] = None
    ) -> List[UsuarioResponseDTO]:
        mecanicos = await user_repository.buscar_mecanicos(db, q=q, exclude_id=exclude_id)
        return [UsuarioResponseDTO.model_validate(m) for m in mecanicos]


auth_service = AuthService()
