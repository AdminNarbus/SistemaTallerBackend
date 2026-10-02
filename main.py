"""
Punto de entrada raíz de compatibilidad para el servidor ASGI Uvicorn.
Permite iniciar el backend ejecutando indistintamente:
  - uvicorn main:app --reload --port 8000
  - python run.py
  - python main.py
"""
from app.main import app
from app.core.config import settings

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.server_host,
        port=settings.PORT,
        reload=settings.is_reload_enabled,
    )

__all__ = ["app"]
