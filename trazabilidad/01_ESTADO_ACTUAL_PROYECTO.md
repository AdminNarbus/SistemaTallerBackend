# Estado Actual del Proyecto: Backend Taller Narbus

## Visión General
El backend de **Narbus Taller** es una API REST construida en FastAPI con base de datos PostgreSQL/MySQL (vía SQLAlchemy async + Alembic). Su objetivo es proveer soporte a los módulos de mantención de buses, control de neumáticos, autenticación de usuarios y auditoría de supervisión.

## Módulos y Estado

| Módulo | Estado | Descripción |
| --- | --- | --- |
| **Auth & Usuarios** | `REFACTORIZADO / COMPLETADO` | Clean Architecture estricta por capas: API desacoplada de ORMs operando 100% con DTOs (`UsuarioResponseDTO`), AuthService agnóstico a HTTP y centralizando seguridad (hashing y verificación de contraseñas), UserRepository como persistencia pura SQL, y autenticación JWT Bearer con caché en memoria. |
| **Buses (Catálogo y Flota Taller)** | `REFACTORIZADO / COMPLETADO` | Clean Architecture estricta por capas: API desacoplada de ORMs operando 100% con DTOs (`UsuarioResponseDTO`, `BusResponseDTO`, `BusSimpleDTO`), BusRepository como persistencia pura SQL sin DTOs, BusService centralizando regla de flota operativa (`200 <= n_bus < 900`) y ordenamiento natural, exportación completa en `dtos/__init__.py`. |
| **Mantención Taller y Pauta Preventiva** | `REFACTORIZADO / COMPLETADO` | Clean Architecture estricta por capas: Router desacoplado de ORMs operando 100% con `UsuarioResponseDTO` en sus 20 endpoints y logging estructurado; Service orquestando reglas de negocio, gobierno transaccional (commit/rollback) y excepciones de dominio; Repository con persistencia pura SQL, consultas atómicas y optimizaciones de 1 sola consulta (single-roundtrip) con CTEs y json_agg; DTOs canónicos tipados para todas las operaciones de taller. |
| **Neumáticos** | `REFACTORIZADO / COMPLETADO` | Clean Architecture estricta por capas: Router desacoplado de ORMs operando con `UsuarioResponseDTO` y logging estándar; Service centralizando validaciones de negocio, seguridad de evidencias fotográficas (extensiones permitidas y tamaño máx 10 MB) con I/O no bloqueante (`asyncio.to_thread`), y gobierno transaccional (commit/rollback); Repository como persistencia pura SQL con flush atómico y sin commits. |
| **Supervisión y Telemetría** | `REFACTORIZADO / COMPLETADO` | Clean Architecture estricta por capas: Router desacoplado de ORMs operando 100% con `UsuarioResponseDTO` y DTOs de auditoría; estructura de paquetes estandarizada con `__init__.py` en dtos, repository, services y api; Service orquestando cálculo de KPIs analíticos y centro de alertas operacionales; Repository con persistencia pura SQL y agregaciones nativas (`func.count`, `group_by`, subconsultas `exists()`), sin llamadas a `commit()`. Cobertura con pruebas unitarias dedicadas. |
| **Core, Database & Security** | `COMPLETADO` | Manejo centralizado de excepciones con respuestas JSON estandarizadas, AuthService desacoplado, eliminación de DDLs en caliente (`db_patch.py`), resolución de límite VARCHAR(32) en Alembic (migración 005) y endpoints seguros de salud (`/health/db` con HTTP 503 y sin leak de stack traces). |
| **Contratos Frontend** | `COMPLETADO` | Especificación completa de contratos REST, schemas TypeScript y ejemplos en `trazabilidad/05_CONTRATOS_API_FRONTEND.md`. |
| **Catálogo de Endpoints y Payloads** | `COMPLETADO` | Diccionario exhaustivo de los 43 endpoints con sus payloads, campos, respuestas y casos de uso en `trazabilidad/06_CATALOGO_ENDPOINTS_PAYLOADS_RESPUESTAS.md`. |

## Arquitectura y Buenas Prácticas
- **Integridad Referencial con Flexibilidad Operativa:** Clave foránea `bus_id` enlazada a `buses.id` con resolución automática a partir de `n_bus` para mantener compatibilidad con flujos de conductores y mecánicos.
- **Unificación de Identidad y Erradicación de Entidades Huérfanas:** Eliminación total de la tabla residual `conductores` y su modelo asociado; la totalidad de los conductores del sistema operan a través del modelo unificado `usuarios` con rol `CONDUCTOR` (`rol_id=1`).
- **Co-responsabilidad Atómica:** Eliminación de líder único piramidal en favor de asignaciones puntuales a averías y control individual de turnos/avances.
- **Optimizaciones de Rendimiento SQL:** Agregaciones nativas `GROUP BY`, filtros `LIKE` indexados por prefijo y eliminación de consultas N+1 en bucles de mecánicos.
- **I/O Asíncrono no Bloqueante:** Escritura de evidencias fotográficas en thread pool con `asyncio.to_thread` para proteger el bucle de eventos principal.
- **Separación Estricta de las 3 Capas (Transversal en Todos los Módulos):**
  - **Routers:** Reciben peticiones HTTP, validan entradas mediante DTOs de Pydantic, extraen `user_id` desde el token JWT y delegan de manera inmediata y exclusiva al Servicio sin saltarse capas ni exponer modelos ORM crudos.
  - **Services:** Concentran el 100% de la lógica de negocio, validan las reglas de taller, orquestan casos de uso, lanzan excepciones de dominio (`BusinessRuleException`, `NotFoundException`, `ConflictException`) y gobiernan de forma explícita el ciclo de vida de las transacciones (`await db.commit()`).
  - **Repositories:** Capa de persistencia pura SQL (SQLAlchemy queries, métodos atómicos `add_*`, `desactivar_mecanicos_activos`, `flush`). **Ningún repositorio ejecuta `await db.commit()`** ni maneja reglas de negocio (eliminación total del anti-patrón *Smart Repository*).
- **Optimización de Contratos y Catálogos Stateless:** El frontend recibe objetos estructurados con `id` (`BusSimpleDTO`, `CategoriaFallaDTO` con `falla_id`) permitiendo enviar directamente `bus_id` y `falla_id` al crear solicitudes de mantención para eliminar consultas intermedias a la BD a 0 RTTs previas. Los catálogos de negocio operan de forma stateless consultando directamente a la base de datos indexada en PostgreSQL/Neon, preservando únicamente la caché en memoria de usuario (`_USER_CACHE`) para optimizar la validación de tokens JWT sin sobrecargar la red.
- **Rendimiento y Listados Ultrarrápidos de 1 Sola Consulta (Single-Roundtrip SQL):**
  - Las vistas de bandeja de entrada (`/pendientes` y `/mis-trabajos`) fueron consolidadas en **exactamente 1 sola consulta SQL nativa** con CTEs (`WITH filtered_solicitudes...`) y agregación JSON (`json_agg`), eliminando la cascada previa de 6 consultas secuenciales de `selectinload`.
  - Se introdujo `SolicitudResumenDTO` (heredero directo de `SolicitudDTO`), que garantiza 100% de compatibilidad con el Frontend mientras reduce los tiempos de respuesta de **4.85s - 5.86s a 0.16s - 0.9s** hacia la nube de Neon en Ohio.
  - Se incorporan cabeceras `Cache-Control: private, max-age=15, stale-while-revalidate=30` en listados para habilitar navegación instantánea en el frontend sin pantallas de carga.
  - Todas las mutaciones operativas del mecánico (`tomar`, `autoasignar`, `check`, `repuesto`, `agregar-falla`, `liberar-turno`, `finalizar`) retornan directamente el `SolicitudDTO` actualizado en memoria tras el commit (0 SELECTs post-commit).
  - La serialización en `_to_solicitud_dto` inspecciona directamente el estado en `__dict__` garantizando total inmunidad frente a lazy loading síncrono no controlado (`MissingGreenlet`).
  - Guías de integración y contratos actualizados en [GUIA_FRONTEND_CONTRATOS_OPTIMIZADOS.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/trazabilidad/GUIA_FRONTEND_CONTRATOS_OPTIMIZADOS.md) y [GUIA_FRONTEND_MODULO_MECANICOS.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/trazabilidad/GUIA_FRONTEND_MODULO_MECANICOS.md).
- **GitFlow:** Desarrollo bajo ramas `feature/*` integradas a `develop`.



