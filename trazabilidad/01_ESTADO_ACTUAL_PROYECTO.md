# Estado Actual del Proyecto: Backend Taller Narbus

## Visión General
El backend de **Narbus Taller** es una API REST construida en FastAPI con base de datos PostgreSQL/MySQL (vía SQLAlchemy async + Alembic). Su objetivo es proveer soporte a los módulos de mantención de buses, control de neumáticos, autenticación de usuarios y auditoría de supervisión.

## Módulos y Estado

| Módulo | Estado | Descripción |
| --- | --- | --- |
| **Auth & Usuarios** | `COMPLETADO` | Autenticación JWT Bearer, gestión de roles (Mecánico, Conductor, Supervisor, Admin) y soft-delete de usuarios. |
| **Buses (Catálogo y Flota Taller)** | `COMPLETADO` | Catálogo de buses/flota centralizado, claves foráneas relacionales (`bus_id`), filtro de flota taller (`200 <= n_bus < 900`), control de presencia física `en_taller` y búsqueda por prefijo (`/buses/buscar`). |
| **Mantención Taller y Pauta Preventiva** | `COMPLETADO` | Asignación atómica de averías con co-responsabilidad multi-mecánico, bitácora cronológica, reporte de falta de repuestos, catálogo de 19 ítems de pauta preventiva, validación estricta de checklist antes de liberación y cierre parcial justificado. |
| **Neumáticos** | `EN PROCESO` | Captura multipart/form-data de formularios de reporte de neumáticos y evidencia fotográfica. |
| **Supervisión y Telemetría** | `COMPLETADO` | Endpoints de trazabilidad inmutable, auditoría global de taller, KPIs en tiempo real (`buses_fisicamente_en_taller`, `fallas_bloqueadas_por_repuesto`) y centro de alertas proactivas (`REPUESTO_FALTANTE`, `DEFECTO_PAUTA`, `BUS_SIN_MECANICOS`). |
| **Core & Exceptions** | `COMPLETADO` | Manejo centralizado de excepciones con respuestas JSON estandarizadas (`NotFoundException`, `BusinessRuleException`, `ConflictException`, `PermissionException`). |
| **Contratos Frontend** | `COMPLETADO` | Especificación completa de contratos REST, schemas TypeScript y ejemplos en `trazabilidad/05_CONTRATOS_API_FRONTEND.md`. |

## Arquitectura y Buenas Prácticas
- **Integridad Referencial con Flexibilidad Operativa:** Clave foránea `bus_id` enlazada a `buses.id` con resolución automática a partir de `n_bus` para mantener compatibilidad con flujos de conductores y mecánicos.
- **Co-responsabilidad Atómica:** Eliminación de líder único piramidal en favor de asignaciones puntuales a averías y control individual de turnos/avances.
- **Excepciones de Dominio:** Sin bloques `try/except` repetitivos en controladores ni lanzamientos genéricos de `ValueError`.
- **GitFlow:** Integración de features completada en `feature/sistema-integral-taller-y-pauta` sincronizada en GitHub.


