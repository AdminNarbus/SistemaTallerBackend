# ==============================================================================
# Dockerfile para Producción: Backend Taller Narbus (Google Cloud Run / VPS)
# ==============================================================================
FROM python:3.12-slim

# Evitar que Python escriba archivos .pyc y habilitar flush inmediato de stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Instalar dependencias del sistema mínimas requeridas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación y migraciones
COPY . .

# Asegurar la existencia del directorio de uploads local (fallback)
RUN mkdir -p uploads/solicitudes uploads/evidencias

# Exponer el puerto por defecto (Cloud Run inyecta la variable $PORT)
EXPOSE 8000

# Comando de inicio compatible con Google Cloud Run ($PORT dinámico)
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
