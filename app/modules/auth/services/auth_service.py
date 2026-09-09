import logging
from typing import Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationException,
    BusinessRuleException,
    ConflictException,
    NotFoundException,
)
from app.core.security import create_access_token, get_password_hash, verify_password
from app.modules.auth.dtos import (
    TokenDTO,
    UsuarioCreateDTO,
    UsuarioLoginDTO,
    UsuarioResponseDTO,
)
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.repository.user_repository import user_repository

logger = logging.getLogger(__name__)


class AuthService:
    """
    Capa de servicio de negocio para autenticación, generación de tokens y gestión de cuentas de usuario.
    Independiente de la capa de transporte/HTTP (FastAPI).
    """

    async def login(self, db: AsyncSession, login_data: UsuarioLoginDTO) -> TokenDTO:
        """
        Caso de Uso: Autenticación de credenciales de usuario y emisión de Token JWT Bearer.
        """
        logger.info("[AUTH] Intento de login | username='%s'", login_data.username)
        user = await user_repository.get_by_username(db, username=login_data.username)
        if not user:
            logger.warning("[AUTH] Intento de login con usuario inexistente: '%s'", login_data.username)
            raise AuthenticationException("Usuario o contraseña incorrectos.")

        if not verify_password(login_data.password, user.password_hash):
            logger.warning("[AUTH] Contraseña inválida para usuario: '%s'", login_data.username)
            raise AuthenticationException("Usuario o contraseña incorrectos.")

        if not user.is_active:
            logger.warning("[AUTH] Intento de login con usuario inactivo: '%s'", login_data.username)
            raise BusinessRuleException("El usuario se encuentra inactivo.")

        access_token = create_access_token(subject=user.id)
        logger.info("[AUTH] Token JWT emitido exitosamente | id=%s | username='%s'", user.id, user.username)

        return TokenDTO(
            access_token=access_token,
            token_type="bearer",
            user=UsuarioResponseDTO.model_validate(user),
        )

    async def login_access_token(
        self, db: AsyncSession, form_data: Any
    ) -> TokenDTO:
        """
        Adaptador de conveniencia para solicitudes con formulario/OAuth2 form.
        Delega en la lógica de negocio centralizada de login.
        """
        login_dto = UsuarioLoginDTO(
            username=form_data.username, password=form_data.password
        )
        return await self.login(db, login_data=login_dto)

    async def register(
        self, db: AsyncSession, usuario_in: UsuarioCreateDTO
    ) -> TokenDTO:
        """
        Caso de Uso: Auto-registro de un nuevo usuario en la plataforma.
        """
        logger.info("[AUTH] Solicitud de registro | username='%s' | rol='%s'", usuario_in.username, usuario_in.rol)
        user_existente = await user_repository.get_by_username(
            db, username=usuario_in.username
        )
        if user_existente:
            raise ConflictException("El nombre de usuario ya está registrado en el sistema.")

        rol_obj = await user_repository.get_or_create_rol(db, usuario_in.rol or "CONDUCTOR")
        password_hash = get_password_hash(usuario_in.password)

        nuevo_usuario = Usuario(
            nombre=usuario_in.nombre,
            apellido=usuario_in.apellido,
            username=usuario_in.username.strip(),
            password_hash=password_hash,
            rol_id=rol_obj.id,
            is_active=usuario_in.is_active if usuario_in.is_active is not None else True,
        )
        await user_repository.add(db, nuevo_usuario)
        await db.commit()
        await db.refresh(nuevo_usuario)

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
        """
        Caso de Uso: Creación administrativa de usuario (desde panel de supervisor o admin).
        """
        logger.info("[AUTH] Creación administrativa de usuario | username='%s' | rol='%s'", usuario_in.username, usuario_in.rol)
        user_existente = await user_repository.get_by_username(
            db, username=usuario_in.username
        )
        if user_existente:
            raise ConflictException("El nombre de usuario ya está registrado en el sistema.")

        rol_obj = await user_repository.get_or_create_rol(db, usuario_in.rol or "CONDUCTOR")
        password_hash = get_password_hash(usuario_in.password)

        nuevo_usuario = Usuario(
            nombre=usuario_in.nombre,
            apellido=usuario_in.apellido,
            username=usuario_in.username.strip(),
            password_hash=password_hash,
            rol_id=rol_obj.id,
            is_active=usuario_in.is_active if usuario_in.is_active is not None else True,
        )
        await user_repository.add(db, nuevo_usuario)
        await db.commit()
        await db.refresh(nuevo_usuario)

        logger.info("[AUTH] Usuario administrativo creado | id=%s | username='%s'", nuevo_usuario.id, nuevo_usuario.username)
        return UsuarioResponseDTO.model_validate(nuevo_usuario)

    async def deshabilitar_usuario(
        self, db: AsyncSession, usuario_id: int, current_user_id: int
    ) -> UsuarioResponseDTO:
        """
        Caso de Uso: Deshabilita la cuenta de un usuario (soft-delete).
        Valida que el supervisor no pueda deshabilitarse a sí mismo y que el usuario exista.
        Gobierna la transacción (commit).
        """
        logger.info("[AUTH] Deshabilitando usuario | id=%s | solicitado_por=%s", usuario_id, current_user_id)
        if current_user_id == usuario_id:
            raise BusinessRuleException(
                "No puedes deshabilitar tu propia cuenta de usuario.", status_code=400
            )

        user = await user_repository.get_by_id(db, user_id=usuario_id)
        if not user:
            raise NotFoundException("El usuario especificado no fue encontrado.")

        await user_repository.desactivar(db, user_or_id=user)
        await db.commit()
        await db.refresh(user)
        return UsuarioResponseDTO.model_validate(user)

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
