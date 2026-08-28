# Contenido y Alcance Técnico del Backend Narbus

## Alcance Incluido
1. **API REST FastAPI:**
   - Documentación Swagger / OpenAPI `/api/v1/openapi.json`.
   - Rotación y verificación de tokens JWT.
2. **Capa de Base de Datos Async:**
   - SQLAlchemy 2.0 Async Session.
   - Parches automáticos y siembra de datos de prueba exclusiva en entorno local (`dev_local`).
3. **Manejo de Archivos Estáticos:**
   - Carga de evidencias en directorio `/uploads/evidencias/`.
4. **Respuesta de Errores Unificada:**
   - Formato JSON estándar `{ "error": { "code": "...", "message": "...", "detail": ... } }`.

## Alcance No Incluido (Out of Scope)
- Despliegue directo a producción desde la rama `main` sin aprobación explicita.
- Modificación directa de datos de producción mediante scripts no auditados.
