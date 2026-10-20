"""Compatibilidad de payloads JSON y multipart para operaciones de taller."""
from typing import List, Tuple, Type, TypeVar, get_args, get_origin

from fastapi import Request, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)


async def parse_json_or_multipart(request: Request, model: Type[T]) -> Tuple[T, List[UploadFile]]:
    """Lee el DTO existente desde JSON o sus campos equivalentes desde multipart."""
    content_type = request.headers.get("content-type", "").lower()
    fotos: List[UploadFile] = []
    try:
        if "multipart/form-data" in content_type:
            form = await request.form()
            payload = {
                field: form.get(field)
                for field in model.model_fields
                if form.get(field) is not None
            }
            # Los campos repetidos en multipart representan listas, igual que
            # los arrays JSON. Esto incluye autores y talleres colaboradores.
            for field, definition in model.model_fields.items():
                annotation = definition.annotation
                es_lista = get_origin(annotation) is list or any(
                    get_origin(arg) is list for arg in get_args(annotation)
                )
                if es_lista:
                    values = form.getlist(field)
                    if values:
                        payload[field] = values
            fotos = [foto for foto in form.getlist("fotos") if getattr(foto, "filename", None)]
        elif "application/json" in content_type:
            payload = await request.json()
        else:
            payload = {}
        return model.model_validate(payload), fotos
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
