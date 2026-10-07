import logging
from typing import List, Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BusinessRuleException,
    ConflictException,
    NotFoundException,
    PermissionException,
)
from app.core.security import create_access_token, create_refresh_token, get_password_hash
from app.core.db_metrics import mark_user_cache
from app.modules.auth.constants import (
    DEFAULT_PAGE_SKIP,
    DEFAULT_PAGE_LIMIT,
    ROLES_PERMITIDOS,
    RolUsuario,
)
from app.modules.auth.dtos import (
    TokenDTO,
    UsuarioCreateDTO,
    UsuarioUpdateDTO,
    UsuarioResponseDTO,
)
from app.modules.auth.models.rol import Rol
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.repository.user_repository import user_repository
from app.modules.auth.user_cache import (
    clear_user_cache,
    get_cached_user,
    set_cached_user,
)
from app.core.realtime.events import RealtimeEvent, publish_event_soon

logger = logging.getLogger(__name__)


class UserService:
    """
    Capa de servicio de negocio para la administración del ciclo de vida de usuarios:
    creación, registro, listado paginado, perfiles y soft-delete.
    """

    async def validar_y_resolver_rol(
        self, db: AsyncSession, rol_solicitado: Optional[str]
    ) -> Rol:
        """Valida pertenencia a RolUsuario y existencia en base de datos."""
        rol_nombre = getattr(rol_solicitado, "value", rol_solicitado) or RolUsuario.CONDUCTOR.value
        rol_str = str(rol_nombre).upper().strip()

        if rol_str not in ROLES_PERMITIDOS:
            raise BusinessRuleException(f"El rol '{rol_solicitado}' no es válido.")

        rol_obj = await user_repository.get_rol_by_nombre(db, rol_str)
        if not rol_obj:
            rol_obj = Rol(nombre=rol_str, descripcion=f"Rol de {rol_str.capitalize()}")
            db.add(rol_obj)
            await db.flush()
        return rol_obj

    async def _crear_usuario_entidad(
        self, db: AsyncSession, usuario_in: UsuarioCreateDTO
    ) -> Usuario:
        """Valida unicidad, resuelve rol, hashea contraseña y persiste la entidad Usuario."""
        user_existente = await user_repository.get_by_username(
            db, username=usuario_in.username
        )
        if user_existente:
            raise ConflictException("El nombre de usuario ya está registrado en el sistema.")

        rol_obj = await self.validar_y_resolver_rol(db, usuario_in.rol)
        password_hash = get_password_hash(usuario_in.password)

        nuevo_usuario = Usuario(
            nombre=usuario_in.nombre,
            apellido=usuario_in.apellido,
            username=usuario_in.username.strip(),
            password_hash=password_hash,
            rol_id=rol_obj.id,
            is_active=usuario_in.is_active if usuario_in.is_active is not None else True,
        )
        nuevo_usuario.rol_rel = rol_obj
        await user_repository.create(db, nuevo_usuario)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictException("El nombre de usuario ya está registrado en el sistema.") from exc
        publish_event_soon(RealtimeEvent(
            resource_type="user", resource_id=nuevo_usuario.id, action="created"
        ))
        return nuevo_usuario

    async def register(
        self, db: AsyncSession, usuario_in: UsuarioCreateDTO
    ) -> TokenDTO:
        """Caso de Uso: Auto-registro de un nuevo usuario en la plataforma."""
        # El registro público nunca puede crear cuentas privilegiadas. El rol
        # recibido del cliente se ignora deliberadamente.
        usuario_in = usuario_in.model_copy(
            update={"rol": RolUsuario.CONDUCTOR, "is_active": True}
        )
        logger.info("[USER-SERVICE] Solicitud de registro | username='%s' | rol='%s'", usuario_in.username, usuario_in.rol)
        nuevo_usuario = await self._crear_usuario_entidad(db, usuario_in)
        access_token = create_access_token(subject=nuevo_usuario.id)
        refresh_token = create_refresh_token(subject=nuevo_usuario.id)
        user_dto = UsuarioResponseDTO.model_validate(nuevo_usuario)
        set_cached_user(nuevo_usuario.id, user_dto)
        logger.info("[USER-SERVICE] Registro exitoso | id=%s | username='%s'", nuevo_usuario.id, nuevo_usuario.username)

        return TokenDTO(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user_dto,
        )

    async def crear_usuario(
        self,
        db: AsyncSession,
        usuario_in: UsuarioCreateDTO,
        actor_rol: Optional[str] = None,
    ) -> UsuarioResponseDTO:
        """Caso de Uso: Creación administrativa de usuario (desde panel de supervisor o admin)."""
        actor_rol_clean = (actor_rol or "").upper().strip()
        requested_role = getattr(usuario_in.rol, "value", usuario_in.rol)
        if requested_role == RolUsuario.ADMIN.value and actor_rol_clean != RolUsuario.ADMIN.value:
            raise PermissionException(
                "Solo un ADMIN puede crear otro usuario con rol ADMIN."
            )
        logger.info("[USER-SERVICE] Creación administrativa de usuario | username='%s' | rol='%s'", usuario_in.username, usuario_in.rol)
        nuevo_usuario = await self._crear_usuario_entidad(db, usuario_in)
        logger.info("[USER-SERVICE] Usuario administrativo creado | id=%s | username='%s'", nuevo_usuario.id, nuevo_usuario.username)
        return UsuarioResponseDTO.model_validate(nuevo_usuario)

    async def deshabilitar_usuario(
        self, db: AsyncSession, usuario_id: int, current_user_id: int
    ) -> UsuarioResponseDTO:
        """Caso de Uso: Deshabilita la cuenta de un usuario (soft-delete)."""
        logger.info("[USER-SERVICE] Deshabilitando usuario | id=%s | solicitado_por=%s", usuario_id, current_user_id)
        if current_user_id == usuario_id:
            raise BusinessRuleException(
                "No puedes deshabilitar tu propia cuenta de usuario.", status_code=400
            )

        user = await user_repository.get_by_id(db, user_id=usuario_id)
        if not user:
            raise NotFoundException("El usuario especificado no fue encontrado.")

        await user_repository.desactivar(db, user)
        await db.commit()
        clear_user_cache(usuario_id)
        publish_event_soon(RealtimeEvent(
            resource_type="user", resource_id=usuario_id,
            action="deactivated", actor_id=current_user_id,
        ))
        from app.core.realtime.runtime import realtime_runtime
        await realtime_runtime.disconnect_user(usuario_id)
        return UsuarioResponseDTO.model_validate(user)

    async def actualizar_usuario(
        self,
        db: AsyncSession,
        usuario_id: int,
        usuario_in: UsuarioUpdateDTO,
        current_user_id: int,
    ) -> UsuarioResponseDTO:
        """Actualiza parcialmente nombre, apellido y teléfono de un usuario."""
        logger.info(
            "[USER-SERVICE] Actualizando datos personales | id=%s | solicitado_por=%s",
            usuario_id,
            current_user_id,
        )
        user = await user_repository.get_by_id(db, user_id=usuario_id)
        if not user:
            raise NotFoundException("El usuario especificado no fue encontrado.")

        payload = usuario_in.model_dump(exclude_unset=True)
        await user_repository.actualizar_datos_personales(
            db,
            user,
            nombre=payload.get("nombre"),
            apellido=payload.get("apellido"),
            telefono=payload.get("telefono"),
        )
        await db.commit()
        clear_user_cache(usuario_id)
        publish_event_soon(RealtimeEvent(
            resource_type="user",
            resource_id=usuario_id,
            action="updated",
            actor_id=current_user_id,
        ))
        return UsuarioResponseDTO.model_validate(user)

    async def get_current_user_profile(
        self, db: AsyncSession, user_id: int
    ) -> Optional[UsuarioResponseDTO]:
        """Obtiene el perfil actual desde BD para validar inmediatamente is_active y rol."""
        cached_user = get_cached_user(user_id)
        if cached_user:
            mark_user_cache("hit")
            return cached_user
        mark_user_cache("miss")
        user = await user_repository.get_by_id(db, user_id=user_id)
        if not user or not user.is_active:
            clear_user_cache(user_id)
            return None

        user_dto = UsuarioResponseDTO.model_validate(user)
        set_cached_user(user_id, user_dto)
        return user_dto

    async def listar_usuarios(
        self,
        db: AsyncSession,
        skip: int = DEFAULT_PAGE_SKIP,
        limit: int = DEFAULT_PAGE_LIMIT,
        rol: Optional[str] = None,
        q: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[UsuarioResponseDTO]:
        """Lista todos los usuarios registrados con soporte de paginación (default: 20) y filtros opcionales."""
        usuarios = await user_repository.get_all(
            db, skip=skip, limit=limit, rol=rol, q=q, is_active=is_active
        )
        return [UsuarioResponseDTO.model_validate(u) for u in usuarios]

    async def contar_usuarios(
        self,
        db: AsyncSession,
        rol: Optional[str] = None,
        q: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> int:
        """Retorna el conteo total de usuarios registrados aplicando los filtros opcionales."""
        return await user_repository.count_usuarios(
            db, rol=rol, q=q, is_active=is_active
        )


user_service = UserService()

__all__ = ["UserService", "user_service"]
