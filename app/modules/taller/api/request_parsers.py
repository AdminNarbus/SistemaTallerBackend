"""Compatibilidad de payloads JSON y multipart para operaciones de taller."""
from typing import List, Tuple, Type, TypeVar

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
            if "mecanicos_ids" in model.model_fields:
                mecanicos_ids = form.getlist("mecanicos_ids")
                if mecanicos_ids:
                    payload["mecanicos_ids"] = mecanicos_ids
            fotos = [foto for foto in form.getlist("fotos") if getattr(foto, "filename", None)]
        elif "application/json" in content_type:
            payload = await request.json()
        else:
            payload = {}
        return model.model_validate(payload), fotos
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
