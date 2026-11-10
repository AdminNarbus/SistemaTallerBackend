# Contenido, Tecnologías y Alcance Técnico del Backend Narbus

AV-0153: búsqueda por prefijo en tabla_ot y tabla_n_bus de GET /dashboard/solicitudes y en q (número/patente) de GET /taller/buses. El autocompletado del dashboard ya usaba prefijo. Filtros globales exactos conservados. Bandejas pendientes/mis-trabajos sin búsqueda textual; no se agregan parámetros nuevos. Verificación: 82 pruebas de regresión y buses aprobadas, más 8 casos nuevos del dashboard aprobados tras corregir un dato de prueba incompatible con una única OT activa por bus.

AV-0152: búsqueda por palabras en nombre/apellido/username compartida por usuarios y mecánicos. Rol VISUAL con consultas habilitadas y escrituras bloqueadas (403), incluidas rutas de autenticación opcional; login y refresh permitidos. Migración 040 y guía docs/ROL_VISUAL_Y_BUSQUEDA_USUARIOS.md. Implementación local; pendiente aplicación al entorno de despliegue e integración del frontend.

AV-0151: script inmediato y servicio mensual comparten preparación de padrón con última ocurrencia por RUT. Modo predeterminado del script: sincronizar existentes y crear faltantes; `--solo-nuevos` conserva la carga limitada opcional. Contadores de habilitados/deshabilitados e informe de registros reemplazados.

AV-0150: script de altas inmediatas en Neon con revisión por defecto y `--aplicar`; sin migraciones ni registro mensual, incorpora solo RUT inexistentes, valida TLS/destino y conserva cuentas existentes. Omisiones identificadas en informe sin credenciales.

CON-SYNC-1: integración HTTP con padrón de conductores y actualización mensual transaccional de usuarios; conserva IDs e historial y protege otros roles. Programación externa con Cloud Scheduler. [Configuración](../docs/SINCRONIZACION_CONDUCTORES.md).

REP-1: catálogo de repuestos vacío y registro de cantidades informativas por falla, con bitácora y anulación trazable. Sin importación Excel ni stock. Ver [contratos de repuestos](GUIA_FRONTEND_REPUESTOS_POR_FALLA.md). Migraciones 037 y 038 pendientes de aplicación al entorno correspondiente.

## Dashboard de taller bajo demanda

Nuevo módulo de lectura con JWT y rol Supervisor/Admin, reutilizando Taller/Buses/Auth sin tablas propias. Calcula en SQL al consultar; no incluye interfaz, archivos del prototipo, almacenamiento de indicadores ni actualización diaria. La API proporciona datos paginados para gráficos, tabla, ficha y exportaciones. [Contrato y matriz de alcance](GUIA_FRONTEND_DASHBOARD.md).

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


## Revisión individual de fallas (2026-11-09)

Implementados `estado_revision`, `revisado_por_id` y `fecha_revision`, aprobación individual por supervisión y aprobación de fallas seleccionadas al asignarse. Reportar sin asignación previa ni autoasignación deja revisión pendiente. Migración 041 preparada, pendiente de aplicar al entorno de despliegue. Contrato y reglas: [Revisión individual de fallas](../docs/REVISION_INDIVIDUAL_FALLAS.md).


## Revisión completa de repuestos (2026-11-09)

Verificados 42 casos de repuestos y 120 de regresión relacionada, sin fallos finales. Migración 038 y concurrencia verificadas en PostgreSQL temporal, sin diferencias entre sus tablas y los modelos. Corregidos edición con ID cero, consistencia UTC, validación de rol actual y aprobación de fallas en la conversión inicial a OT, manteniendo el alcance selectivo al asignarse. No se aplicaron migraciones a bases externas. Evidencias y límites: [Informe de revisión](../docs/REVISION_REPUESTOS_20261109.md).


Guía de integración pendiente en frontend: [Revisión individual de fallas](GUIA_FRONTEND_REVISION_FALLAS.md), con contrato, aprobación selectiva, permisos, manejo de caché y checklist de aceptación. Documentada el 2026-11-09.


### Permanencia física en taller — 2026-11-10

Auditoría expone tiempo_taller, horas_en_taller y horas_taller_acumuladas con suma de visitas físicas y congelación de OTs cerradas. La ficha de bus incluye horas_taller_totales agregado en SQL sobre todas sus OTs. Sin migraciones. Contrato: docs/HORAS_REALES_TALLER.md. Verificación: 61 pruebas aprobadas.
