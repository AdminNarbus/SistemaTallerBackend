# Plan de Implementación Backend

## Fase 1: Arquitectura Base y Autenticación
- [x] Configuración de FastAPI y conexión Async SQLAlchemy.
- [x] Implementación de modelo 3NF y migraciones Alembic.
- [x] Endpoints de autenticación JWT.

## Fase 2: Módulo Taller y Registro de Fallas
- [x] Normalización de catálogo de fallas y categorías.
- [x] Workflow de asignación de mecánicos (Líder / Colaboradores).
- [x] Entrega de turno y desasignación individual.
- [x] Bitácora cronológica de comentarios.

## Fase 3: Excepciones Centralizadas y Trazabilidad
- [x] Definición de excepciones de dominio en `app/core/exceptions.py`.
- [x] Handlers globales registrados en `app/main.py`.
- [x] Creación del estándar de trazabilidad y carpeta `.agents/`.

## Fase 4: Pruebas Unitarias, Integración y Sistema (Testing)
- [x] Implementación de logging estructurado (`logging.getLogger(__name__)`) en todos los servicios y repositorios.
- [x] Creación y ejecución de suite de pruebas unitarias, integración y sistema E2E automatizadas con Pytest (30/30 tests aprobados).

## Fase 5: Validación Local, Auditoría y Reordenamiento de Capas
- [x] Pruebas locales de integración E2E en entorno `dev_local` (Endpoints Auth, Mantención, Neumáticos y Excepciones).
- [x] Verificación de siembra de datos de prueba en memoria (`aiosqlite:///:memory:`).
- [x] Validación de respuestas HTTP, DTOs y encabezados de error en cliente local.
- [x] Separación estricta de las 3 capas (`Router` -> `Service` -> `Repository`) en todos los módulos (Auth, Buses, Mantención, Neumáticos, Supervisión), erradicando Smart Repositories con commits y bucles manuales de persistencia en servicios.
- [x] Estandarización de comentarios predeterminados en bitácora de la OT (inicio, check de fallas, repuestos, avance, cierre) con nombres legibles y eliminación de IDs internos.
- [x] Suite de 61 pruebas automatizadas aprobadas al 100% sin regresiones.

## Fase 6: Control de Versiones Git y Despliegue en la Nube
- [x] Consolidación de ramas de características mediante GitFlow (`develop`).
- [x] Configuración de pipeline CI/CD en Google Cloud Build (`cloudbuild.yaml`) sincronizado con Git.
- [x] Empaquetado Docker con auto-migraciones de esquema (`docker-entrypoint.sh` + `alembic upgrade head`).
- [x] Despliegue Serverless en Google Cloud Run con Artifact Registry y Secret Manager.
- [x] Guía operativa y manual de despliegue (`GUIA_DEPLOY_GOOGLE_CLOUD_BUILD_RUN.md`).
- [ ] Etiquetado de versión de release (Git Tagging para producción).
- [ ] Despliegue y verificación en vivo con dominio asignado.

## Fase 7: Gestión Integral de Flota de Buses y Control Administrativo de Estados de OTs (Supervisión)
- [x] Migración Alembic 011 para campos de auditoría (`fecha_creacion`, `fecha_baja`, `motivo_baja`, `usuario_baja_id`).
- [x] Eliminación de filtro estático numérico de flota (`200 <= n_bus < 900`) para catalogación y búsqueda integral de la flota completa.
- [x] Endpoints para alta (`POST /api/v1/buses`), baja auditada (`PATCH /api/v1/buses/{id}/dar-de-baja`, `DELETE`) y reactivación (`PATCH /api/v1/buses/{id}/reactivar`).
- [x] Transición administrativa de estados de OTs (`PATCH /api/v1/supervision/solicitudes/{id}/estado`) con bitácora `CAMBIO_ESTADO`, justificación opcional, liberación condicional de taller y reaperturas automáticas.
- [x] Cobertura completa de tests unitarios y de integración (154/154 tests verdes al 100%).
