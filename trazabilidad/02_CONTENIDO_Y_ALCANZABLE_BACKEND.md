# Contenido, Tecnologías y Alcance Técnico del Backend Narbus

## Tecnologías Utilizadas (Tech Stack)

### Core & Framework Web
- **Python 3.10+**: Lenguaje base del proyecto.
- **FastAPI (>= 0.110.0)**: Framework web asíncrono para la construcción de la API REST.
- **Uvicorn (>= 0.28.0)**: Servidor web ASGI de alto rendimiento para la ejecución de FastAPI.

### Base de Datos y ORM
- **SQLAlchemy (>= 2.0.28)**: ORM asíncrono (`AsyncSession`) para el mapeo y gestión de modelos relacionales.
- **Alembic (>= 1.13.1)**: Herramienta de gestión y control de versiones de migraciones de base de datos.
- **asyncpg (>= 0.29.0)** / **psycopg2-binary (>= 2.9.9)**: Controladores y adaptadores para la conexión asíncrona a PostgreSQL.

### Validaciones y DTOs
- **Pydantic (>= 2.6.4)**: Validación de esquemas de datos y construcción de DTOs (Data Transfer Objects).
- **Pydantic-Settings (>= 2.2.1)**: Gestión de variables de entorno y configuración centralizada.

### Seguridad y Utilidades
- **PyJWT / Passlib (Bcrypt)**: Generación, firma y verificación de tokens JWT Bearer, así como encriptado de contraseñas.
- **python-dotenv (>= 1.0.1)**: Carga de variables de entorno desde archivos `.env`.
- **python-multipart (>= 0.0.9)**: Procesamiento de archivos multipart/form-data (subida de fotos e imágenes de evidencia).

---

## Alcance Incluido

1. **API REST FastAPI:**
   - Documentación interactiva Swagger UI / OpenAPI `/api/v1/openapi.json`.
   - Autenticación, rotación y verificación de tokens JWT Bearer.
2. **Capa de Base de Datos Async:**
   - SQLAlchemy 2.0 Async Session.
   - Parches automáticos y siembra de datos de prueba exclusiva en entorno local (`dev_local`).
3. **Manejo de Archivos Estáticos:**
   - Carga de evidencias en directorio `/uploads/evidencias/`.
4. **Respuesta de Errores Unificada:**
   - Formato JSON estándar `{ "error": { "code": "...", "message": "...", "detail": ... } }`.

---

## Alcance No Incluido (Out of Scope)
- Despliegue directo a producción desde la rama `main` sin aprobación explícita.
- Modificación directa de datos de producción mediante scripts no auditados.
