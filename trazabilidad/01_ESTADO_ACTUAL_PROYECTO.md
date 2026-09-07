# Estado Actual del Proyecto: Backend Taller Narbus

## Visión General
El backend de **Narbus Taller** es una API REST construida en FastAPI con base de datos PostgreSQL/MySQL (vía SQLAlchemy async + Alembic). Su objetivo es proveer soporte a los módulos de mantención de buses, control de neumáticos, autenticación de usuarios y auditoría de supervisión.

## Módulos y Estado

| Módulo | Estado | Descripción |
| --- | --- | --- |
| **Auth & Usuarios** | `COMPLETADO` | Autenticación JWT Bearer, gestión de roles (Mecánico, Conductor, Supervisor, Admin) y soft-delete de usuarios. |
| **Buses (Catálogo y Flota Taller)** | `COMPLETADO` | Catálogo de buses/flota centralizado, claves foráneas relacionales (`bus_id`), filtro de flota taller (`200 <= n_bus < 900`), control de presencia física `en_taller` y búsqueda por prefijo (`/buses/buscar`). |
| **Mantención Taller y Pauta Preventiva** | `COMPLETADO` | Reporte simplificado de conductor por 6 categorías macro (`categoria_id`), asignación atómica de averías con co-responsabilidad multi-mecánico, bitácora cronológica con comentarios predeterminados legibles para usuarios (sin exposición de IDs numéricos internos), registro automático de resolución/reapertura de averías, reporte de falta de repuestos, catálogo de 11 ítems de pauta preventiva exclusiva para mecánicos, validación estricta de checklist antes de liberación y cierre parcial justificado. |
| **Neumáticos** | `COMPLETADO` | Captura multipart/form-data de formularios de reporte de neumáticos y persistencia asíncrona de evidencias fotográficas (`asyncio.to_thread`). |
| **Supervisión y Telemetría** | `COMPLETADO` | Endpoints de trazabilidad inmutable, auditoría global de taller, KPIs en tiempo real con agregaciones SQL nativas (`buses_fisicamente_en_taller`, `fallas_bloqueadas_por_repuesto`) y centro de alertas proactivas (`REPUESTO_FALTANTE`, `DEFECTO_PAUTA`, `BUS_SIN_MECANICOS`). |
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
- **GitFlow:** Desarrollo bajo ramas `feature/*` integradas a `develop`.


