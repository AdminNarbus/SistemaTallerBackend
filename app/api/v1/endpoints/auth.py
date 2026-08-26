from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Body, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, require_current_user
from app.core.security import create_access_token
from app.crud.crud_usuario import (
    autenticar_usuario,
    crear_usuario,
    get_usuario_by_username,
)
from app.models.usuario import Usuario
from app.schemas.token import Token
from app.schemas.usuario import UsuarioCreate, UsuarioLogin, UsuarioResponse

router = APIRouter()


@router.post(
    "/login",
    response_model=Token,
    summary="Iniciar sesión de usuario",
    status_code=status.HTTP_200_OK,
)
async def login(
    payload: Optional[UsuarioLogin] = Body(None),
    form_data: Optional[OAuth2PasswordRequestForm] = Depends(None),
    db: AsyncSession = SessionDep,
) -> Any:
    """
    Endpoint para autenticación de usuario.
    Acepta tanto JSON (Payload) como Form Data (OAuth2 standard).
    Retorna el Token JWT Bearer y los datos del perfil de usuario.
    """
    username: Optional[str] = None
    password: Optional[str] = None

    if payload and payload.username:
        username = payload.username
        password = payload.password
    elif form_data and form_data.username:
        username = form_data.username
        password = form_data.password

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar usuario y contraseña para iniciar sesión.",
        )

    user = await autenticar_usuario(db, username=username, password=password)
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

    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UsuarioResponse.model_validate(user),
    )


@router.post(
    "/register",
    response_model=Token,
    summary="Registrar un nuevo usuario",
    status_code=status.HTTP_201_CREATED,
)
async def register(
    usuario_in: UsuarioCreate,
    db: AsyncSession = SessionDep,
) -> Any:
    """
    Registra un nuevo usuario en la base de datos y retorna su token de acceso.
    """
    user_existente = await get_usuario_by_username(db, username=usuario_in.username)
    if user_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario ya está registrado en el sistema.",
        )

    nuevo_usuario = await crear_usuario(db, usuario_in=usuario_in)
    access_token = create_access_token(subject=nuevo_usuario.id)

    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UsuarioResponse.model_validate(nuevo_usuario),
    )


@router.get(
    "/me",
    response_model=UsuarioResponse,
    summary="Obtener perfil del usuario actual logueado",
)
async def get_me(
    current_user: Usuario = Depends(require_current_user),
) -> Any:
    """
    Devuelve la información del usuario autenticado que envió el Token Bearer.
    """
    return current_user
