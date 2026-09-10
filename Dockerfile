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

# Asegurar la existencia de directorios y permisos de ejecución del entrypoint
RUN mkdir -p uploads/solicitudes uploads/evidencias && \
    chmod +x /app/docker-entrypoint.sh

# Exponer el puerto por defecto (Cloud Run inyecta la variable $PORT)
EXPOSE 8000

# Punto de entrada para migraciones automáticas y arranque del servicio
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn"]
