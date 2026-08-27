from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    SessionDep,
    require_current_user,
    require_supervisor_or_admin,
)
from app.core.security import create_access_token
from app.modules.auth.dtos import (
    TokenDTO,
    UsuarioCreateDTO,
    UsuarioLoginDTO,
    UsuarioResponseDTO,
)
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.repository.user_repository import user_repository

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
    user = await user_repository.authenticate(
        db, username=login_data.username, password=login_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario se encuentra inactivo.",
        )

    access_token = create_access_token(subject=user.id)

    return TokenDTO(
        access_token=access_token,
        token_type="bearer",
        user=UsuarioResponseDTO.model_validate(user),
    )


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
    user = await user_repository.authenticate(
        db, username=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario se encuentra inactivo.",
        )

    access_token = create_access_token(subject=user.id)

    return TokenDTO(
        access_token=access_token,
        token_type="bearer",
        user=UsuarioResponseDTO.model_validate(user),
    )


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
    user_existente = await user_repository.get_by_username(
        db, username=usuario_in.username
    )
    if user_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario ya está registrado en el sistema.",
        )

    nuevo_usuario = await user_repository.create(db, usuario_in=usuario_in)
    access_token = create_access_token(subject=nuevo_usuario.id)

    return TokenDTO(
        access_token=access_token,
        token_type="bearer",
        user=UsuarioResponseDTO.model_validate(nuevo_usuario),
    )


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
    usuarios = await user_repository.get_all(db, skip=skip, limit=limit)
    return usuarios


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
    user_existente = await user_repository.get_by_username(
        db, username=usuario_in.username
    )
    if user_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario ya existe.",
        )

    nuevo_usuario = await user_repository.create(db, usuario_in=usuario_in)
    return nuevo_usuario


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

    user_desactivado = await user_repository.desactivar(db, user_id=usuario_id)
    if not user_desactivado:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario especificado no fue encontrado.",
        )

    return user_desactivado
