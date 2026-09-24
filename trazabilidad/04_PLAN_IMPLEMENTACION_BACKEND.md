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

## Fase 8: Unificación de 4 Estados Canónicos y Telemetría de Estadías Físicas de Taller
- [x] Unificación en 4 estados canónicos estrictos (`PENDIENTE`, `EN_REPARACION`, `LIBERADO`, `FINALIZADO`) eliminando el estado residual `REPORTADO`.
- [x] Migración Alembic 014 con creación de tabla `taller_solicitud_estadias` y normalización de solicitudes históricas a `PENDIENTE`.
- [x] Cálculo desacoplado de demora en primer ingreso a maestranza (`horas_demora_primer_ingreso = fecha_primer_ingreso_taller - fecha_creacion`).
- [x] Telemetría inmutable de cada ciclo físico en taller (`taller_solicitud_estadias`) con número de visita (#1, #2...), duración exacta por estadía y motivo de egreso (`LIBERADO` o `FINALIZADO`).
- [x] Pausa en ruta: cuando la OT pasa a `LIBERADO`, el bus sale físicamente del taller (`bus.en_taller = False`), la estadía se cierra y el cronómetro de taller se congela en `horas_taller_acumuladas`.
- [x] Reingreso y reapertura: al retomar labores sobre una OT en `LIBERADO`, el bus reingresa (`bus.en_taller = True`), la OT pasa a `EN_REPARACION` y se abre automáticamente la estadía de visita #N+1.
- [x] Redacción de guía detallada de integración para el frontend (`trazabilidad/GUIA_FRONTEND_ESTADOS_Y_CRONOMETRO_TALLER.md`).
- [x] 100% de la suite de pruebas unitarias, de integración y E2E aprobada (182/182 tests verdes).

## Fase 9: Desacoplamiento de Categorías en Fallas y Adopción de Averías Específicas Directas
- [x] Base de datos local PostgreSQL estricta (`127.0.0.1:5432/narbus_taller_db`) configurada en `.env` y migrada a versión `014` (`alembic upgrade head`).
- [x] Eliminación de raíz de la dependencia obligatoria de categorías y catálogos en el flujo de averías de taller.
- [x] Unificación del concepto de falla a un único texto directo (`nombre` / `falla_nombre`), erradicando la ambigüedad entre "nombre" y "descripción".
- [x] Ingesta directa en `create_solicitud` y `agregar_falla_a_solicitud` sin forzar la creación de categorías ni averías artificiales.
- [x] Proyección con `COALESCE(d.descripcion_personalizada, f.nombre, 'Avería')` en las consultas CTE SQL nativas de `list_pendientes`, `list_liberadas`, `list_finalizadas` y `list_auditoria_buses`.
- [x] Documento técnico para el frontend `GUIA_FRONTEND_ELIMINACION_CATEGORIAS.md` detallando payloads simplificados.
- [x] Registro de trazabilidad `0087_20260923T172800Z_eliminacion_categorias_fallas_directas.json`.
- [x] Verificación 100% aprobada en base de datos local: 130 tests unitarios y 45 tests de integración verdes sin regresiones.

