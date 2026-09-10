#!/bin/sh
# ==============================================================================
# Script de Entrada de Producción: Backend Taller Narbus
# ==============================================================================
# 1. Aplica migraciones pendientes de Alembic automáticamente hacia Neon.
# 2. Inicia el servidor ASGI Uvicorn en el puerto asignado dinámicamente ($PORT).
# ==============================================================================
set -e

echo "==> [Entrypoint] Inicializando contenedor de Backend Taller Narbus..."

# Ejecución automática de migraciones con Alembic
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "==> [Alembic] Aplicando migraciones de base de datos (alembic upgrade head)..."
    alembic upgrade head
    echo "==> [Alembic] Migraciones completadas exitosamente."
else
    echo "==> [Alembic] Omitiendo migraciones automáticas (RUN_MIGRATIONS=${RUN_MIGRATIONS})."
fi

# Resolución de puerto dinámico (Cloud Run inyecta la variable $PORT)
PORT="${PORT:-8000}"

# Si el comando es uvicorn o está vacío, arrancar uvicorn con el puerto resuelto
if [ "$1" = "uvicorn" ] || [ -z "$1" ]; then
    echo "==> [Uvicorn] Iniciando servidor en el puerto ${PORT}..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
else
    echo "==> [Custom Command] Ejecutando: $@"
    exec "$@"
fi
