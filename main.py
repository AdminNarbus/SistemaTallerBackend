"""
Punto de entrada raíz de compatibilidad para el servidor ASGI Uvicorn.
Permite iniciar el backend ejecutando indistintamente:
  - uvicorn main:app --reload --port 8000
  - uvicorn app.main:app --reload --port 8000
  - python run.py
"""
from app.main import app

__all__ = ["app"]
