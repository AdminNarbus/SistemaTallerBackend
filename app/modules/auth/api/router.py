import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionDep,
    require_current_user,
    require_supervisor_or_admin,
)
from app.core.exceptions import NotFoundException
from app.modules.auth.dtos import (
    TokenDTO,
    UsuarioCreateDTO,
    UsuarioLoginDTO,
    UsuarioResponseDTO,
)
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.services.auth_service import auth_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/login",
    response_model=TokenDTO,
    summary="Iniciar sesión de usuario (JSON)",
    status_code=status.HTTP_200_OK,
)
async def login(
    login_data: UsuarioLoginDTO,
    db: AsyncSession = SessionDep,
) -> Any:
    """
    Endpoint para autenticación de usuario vía JSON payload.
    Retorna el Token JWT Bearer y los datos del perfil de usuario.
    """
    return await auth_service.login(db, login_data=login_data)


@router.post(
    "/login/token",
    response_model=TokenDTO,
    summary="Iniciar sesión vía OAuth2 Form (Swagger UI / Form Data)",
    status_code=status.HTTP_200_OK,
)
async def login_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = SessionDep,
) -> Any:
    """
    Endpoint compatible con OAuth2 Password Flow (Form Data).
    """
    return await auth_service.login_access_token(db, form_data=form_data)


@router.post(
    "/register",
    response_model=TokenDTO,
    summary="Registrar un nuevo usuario",
    status_code=status.HTTP_201_CREATED,
)
async def register(
    usuario_in: UsuarioCreateDTO,
    db: AsyncSession = SessionDep,
) -> Any:
    """
    Registra un nuevo usuario en la base de datos y retorna su token de acceso.
    """
    return await auth_service.register(db, usuario_in=usuario_in)


@router.get(
    "/me",
    response_model=UsuarioResponseDTO,
    summary="Obtener perfil del usuario actual logueado",
)
async def get_me(
    current_user: Usuario = Depends(require_current_user),
) -> Any:
    """
    Devuelve la información del usuario autenticado que envió el Token Bearer.
    """
    return current_user


@router.get(
    "/mecanicos/buscar",
    response_model=List[UsuarioResponseDTO],
    summary="Buscar mecánicos activos por nombre o query string (Autocomplete)",
)
@router.get(
    "/mecanicos",
    response_model=List[UsuarioResponseDTO],
    summary="Listar/Buscar mecánicos activos (Autocomplete)",
)
async def buscar_mecanicos(
    q: Optional[str] = Query("", description="Texto a buscar por nombre, apellido o username. Si está vacío, retorna todos."),
    exclude_id: Optional[int] = Query(None, description="ID de usuario a excluir de los resultados (ej: el mecánico logueado)"),
    db: AsyncSession = SessionDep,
    current_user: Usuario = Depends(require_current_user),
) -> Any:
    """
    Endpoint para el buscador/autocompletar de mecánicos en el frontend.
    """
    logger.info("[AUTH] Búsqueda de mecánicos | q='%s' | exclude_id=%s | usuario_solicitante_id=%s", q, exclude_id, current_user.id)
    return await auth_service.buscar_mecanicos(db, q=q, exclude_id=exclude_id)


# =====================================================================
# ENDPOINTS DE GESTIÓN DE USUARIOS (SUPERVISOR / ADMIN)
# =====================================================================


@router.get(
    "/usuarios",
    response_model=List[UsuarioResponseDTO],
    summary="Listar usuarios registrados (Solo SUPERVISOR o ADMIN)",
)
async def listar_usuarios(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = SessionDep,
    current_user: Usuario = Depends(require_supervisor_or_admin),
) -> Any:
    """
    Retorna la lista completa de usuarios del sistema.
    Exige rol de SUPERVISOR o ADMIN.
    """
    return await auth_service.listar_usuarios(db, skip=skip, limit=limit)


@router.post(
    "/usuarios",
    response_model=UsuarioResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un usuario desde panel de administración (Solo SUPERVISOR o ADMIN)",
)
async def crear_usuario_supervisor(
    usuario_in: UsuarioCreateDTO,
    db: AsyncSession = SessionDep,
    current_user: Usuario = Depends(require_supervisor_or_admin),
) -> Any:
    """
    Permite a un Supervisor o Admin registrar un usuario (Conductor, Mecánico, Supervisor, etc.).
    """
    return await auth_service.crear_usuario(db, usuario_in=usuario_in)


@router.delete(
    "/usuarios/{usuario_id}",
    response_model=UsuarioResponseDTO,
    summary="Deshabilitar usuario / Soft delete (Solo SUPERVISOR o ADMIN)",
)
async def deshabilitar_usuario(
    usuario_id: int,
    db: AsyncSession = SessionDep,
    current_user: Usuario = Depends(require_supervisor_or_admin),
) -> Any:
    """
    Deshabilita la cuenta de un usuario estableciendo `is_active = False`.
    No borra la fila físicamente para garantizar la trazabilidad de reportes y mantenimientos.
    Exige rol de SUPERVISOR o ADMIN.
    """
    if current_user.id == usuario_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes deshabilitar tu propia cuenta de usuario.",
        )

    from app.modules.auth.repository.user_repository import user_repository
    user_desactivado = await user_repository.desactivar(db, user_id=usuario_id)
    if not user_desactivado:
        raise NotFoundException("El usuario especificado no fue encontrado.")

    return user_desactivado
