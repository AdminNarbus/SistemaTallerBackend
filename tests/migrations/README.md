# Regresión JSON/JSONB de migraciones

Desde la raíz del backend, ejecutar:

`python tests/migrations/test_jsonb_migrations.py`

Requiere Python y los binarios de PostgreSQL para Windows. TEST_PG_BIN permite indicar otra carpeta; por defecto se usa PostgreSQL 16. Si no están disponibles, las pruebas se omiten explícitamente. No requiere dependencias Python adicionales.

El ejecutor crea un clúster temporal con puerto libre y escucha solo en 127.0.0.1. No lee .env, settings ni URLs de bases externas. Prueba el SQL extraído directamente de 021a y la expresión compartida por auditoría y CHECK en 022. Al finalizar detiene el servidor y elimina el clúster temporal.

Cubre JSON y JSONB: normalización de string/número/objeto, conservación del payload original, arrays existentes y rechazo de arrays vacíos/múltiples, escalares, booleanos y valores nulos por la regla de rueda única.

Para reintentar la actualización en producción, usar el código corregido, comprobar primero `alembic current` y después ejecutar `alembic upgrade head` mediante el proceso habitual de migración. No marcar la revisión fallida como aplicada con stamp. Estas pruebas no ejecutan el resto de las migraciones ni comprueban los datos actuales de producción.
