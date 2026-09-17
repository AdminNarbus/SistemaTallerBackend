import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionDep,
    require_current_user,
    require_supervisor_or_admin,
)
from app.modules.auth.constants import DEFAULT_PAGE_SKIP, DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from app.modules.auth.dtos import (
    TokenDTO,
    UsuarioCreateDTO,
    UsuarioLoginDTO,
    UsuarioResponseDTO,
)
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
) -> TokenDTO:
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
) -> TokenDTO:
    """
    Endpoint compatible con OAuth2 Password Flow (Form Data).
    """
    login_dto = UsuarioLoginDTO(username=form_data.username, password=form_data.password)
    return await auth_service.login(db, login_data=login_dto)


@router.post(
    "/register",
    response_model=TokenDTO,
    summary="Registrar un nuevo usuario",
    status_code=status.HTTP_201_CREATED,
)
async def register(
    usuario_in: UsuarioCreateDTO,
    db: AsyncSession = SessionDep,
) -> TokenDTO:
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
    current_user: UsuarioResponseDTO = Depends(require_current_user),
) -> UsuarioResponseDTO:
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
    response: Response,
    q: Optional[str] = Query("", description="Texto a buscar por nombre, apellido o username. Si está vacío, retorna todos."),
    exclude_id: Optional[int] = Query(None, description="ID de usuario a excluir de los resultados (ej: el mecánico logueado)"),
    skip: int = Query(DEFAULT_PAGE_SKIP, ge=0, description="Número de registros a omitir para paginación"),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT, description="Número máximo de mecánicos a retornar (default: 20)"),
    db: AsyncSession = SessionDep,
    current_user: UsuarioResponseDTO = Depends(require_current_user),
) -> List[UsuarioResponseDTO]:
    """
    Endpoint para el buscador/autocompletar de mecánicos en el frontend.
    """
    total = await auth_service.contar_mecanicos(db, q=q, exclude_id=exclude_id)
    response.headers["X-Total-Count"] = str(total)
    logger.info("[AUTH] Búsqueda de mecánicos | q='%s' | exclude_id=%s | skip=%d | limit=%d | total=%d | usuario_solicitante_id=%s", q, exclude_id, skip, limit, total, current_user.id)
    return await auth_service.buscar_mecanicos(db, q=q, exclude_id=exclude_id, skip=skip, limit=limit)


# =====================================================================
# ENDPOINTS DE GESTIÓN DE USUARIOS (SUPERVISOR / ADMIN)
# =====================================================================


@router.get(
    "/usuarios",
    response_model=List[UsuarioResponseDTO],
    summary="Listar usuarios registrados (Solo SUPERVISOR o ADMIN)",
)
async def listar_usuarios(
    response: Response,
    skip: int = Query(DEFAULT_PAGE_SKIP, ge=0, description="Número de usuarios a omitir para paginación"),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT, description="Número máximo de usuarios por página (default: 20)"),
    rol: Optional[str] = Query(None, description="Filtrar por nombre de rol (ADMIN, SUPERVISOR, MECANICO, CONDUCTOR)"),
    q: Optional[str] = Query(None, description="Búsqueda por texto en nombre, apellido o username"),
    is_active: Optional[bool] = Query(None, description="Filtrar por estado activo/inactivo"),
    db: AsyncSession = SessionDep,
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
) -> List[UsuarioResponseDTO]:
    """
    Retorna la lista de usuarios del sistema con soporte de paginación (default: 20 por página)
    y filtros opcionales. El total de registros coincidentes se expone en la cabecera X-Total-Count.
    Exige rol de SUPERVISOR o ADMIN.
    """
    total = await auth_service.contar_usuarios(db, rol=rol, q=q, is_active=is_active)
    response.headers["X-Total-Count"] = str(total)
    return await auth_service.listar_usuarios(
        db, skip=skip, limit=limit, rol=rol, q=q, is_active=is_active
    )


@router.post(
    "/usuarios",
    response_model=UsuarioResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un usuario desde panel de administración (Solo SUPERVISOR o ADMIN)",
)
async def crear_usuario_supervisor(
    usuario_in: UsuarioCreateDTO,
    db: AsyncSession = SessionDep,
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
) -> UsuarioResponseDTO:
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
    current_user: UsuarioResponseDTO = Depends(require_supervisor_or_admin),
) -> UsuarioResponseDTO:
    """
    Deshabilita la cuenta de un usuario estableciendo `is_active = False`.
    No borra la fila físicamente para garantizar la trazabilidad de reportes y mantenimientos.
    Exige rol de SUPERVISOR o ADMIN.
    """
    return await auth_service.deshabilitar_usuario(
        db, usuario_id=usuario_id, current_user_id=current_user.id
    )
