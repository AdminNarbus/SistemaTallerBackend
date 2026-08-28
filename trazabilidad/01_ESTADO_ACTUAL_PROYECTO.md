# Estado Actual del Proyecto: Backend Taller Narbus

## Visión General
El backend de **Narbus Taller** es una API REST construida en FastAPI con base de datos PostgreSQL/MySQL (vía SQLAlchemy async + Alembic). Su objetivo es proveer soporte a los módulos de mantención de buses, control de neumáticos, autenticación de usuarios y auditoría de supervisión.

## Módulos y Estado

| Módulo | Estado | Descripción |
| --- | --- | --- |
| **Auth & Usuarios** | `COMPLETADO` | Autenticación JWT Bearer, gestión de roles (Mecánico, Conductor, Supervisor, Admin) y soft-delete de usuarios. |
| **Mantención Taller** | `COMPLETADO` | Flujo de solicitudes de taller (Reportado, En Reparación, Entregado/Liberado, Finalizado), asignación de mecánico líder y colaboradores, bitácora de comentarios. |
| **Neumáticos** | `EN PROCESO` | Captura multipart/form-data de formularios de reporte de neumáticos y evidencia fotográfica. |
| **Supervisión** | `COMPLETADO` | Endpoints de trazabilidad inmutable y auditoría global de taller para supervisores. |
| **Core & Exceptions** | `COMPLETADO` | Manejo centralizado de excepciones con respuestas JSON estandarizadas (`NotFoundException`, `BusinessRuleException`, `ConflictException`, `PermissionException`). |

## Arquitectura y Buenas Prácticas
- **3NF Normalizado:** Eliminación de redundancias en buses (referenciados directamente por `n_bus`).
- **Excepciones de Dominio:** Sin bloques `try/except` repetitivos en controladores ni lanzamientos genéricos de `ValueError`.
- **GitFlow:** Integración estricta de features hacia la rama `develop`.
