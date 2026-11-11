# Plan de Implementación Backend

AV-0153: búsqueda por prefijo en tabla_ot y tabla_n_bus de GET /dashboard/solicitudes y en q (número/patente) de GET /taller/buses. El autocompletado del dashboard ya usaba prefijo. Filtros globales exactos conservados. Bandejas pendientes/mis-trabajos sin búsqueda textual; no se agregan parámetros nuevos. Verificación: 82 pruebas de regresión y buses aprobadas, más 8 casos nuevos del dashboard aprobados tras corregir un dato de prueba incompatible con una única OT activa por bus.

AV-0152: búsqueda por palabras en nombre/apellido/username compartida por usuarios y mecánicos. Rol VISUAL con consultas habilitadas y escrituras bloqueadas (403), incluidas rutas de autenticación opcional; login y refresh permitidos. Migración 040 y guía docs/ROL_VISUAL_Y_BUSQUEDA_USUARIOS.md. Implementación local; pendiente aplicación al entorno de despliegue e integración del frontend.

## AV-0151 — Sincronización completa y último registro por RUT

- [x] Compartir preparación de la fuente entre automático y script; prevalece última ocurrencia.
- [x] Cambiar el script a altas y actualización de existentes por defecto.
- [x] Aplicar a Neon: 21 nuevos, 49 actualizados, 15 deshabilitados.
- [x] Verificar 353 RUT coincidentes, cero faltantes y cero diferencias de estado/datos.
- [x] Aprobar 43 pruebas, incluidas reactivación/desactivación en ambos modos y PostgreSQL temporal.
- [ ] Corregir en la fuente los 9 registros sin RUT válido; los duplicados ya están resueltos por regla explícita.
- [ ] Desplegar y activar el job mensual conforme a la guía operativa.

## AV-0150 — Altas urgentes en Neon

- [x] Script de revisión y aplicación sin esperar al calendario mensual.
- [x] 207 altas confirmadas el 05-11-2026; 100 cuentas existentes intactas.
- [x] Verificación remota posterior: 307 cuentas procesables existentes, cero nuevas pendientes.
- [x] 37 pruebas de importador, sincronización, API y PostgreSQL temporal aprobadas.
- [ ] Resolver en la fuente 9 RUT inválidos y 94 registros en grupos duplicados contradictorios antes de activar la sincronización mensual estricta.

## CON-SYNC-1 — Sincronización mensual de conductores

- [x] Fuente HTTP validada, servicio y repositorio con commit único y lock PostgreSQL.
- [x] Credenciales por RUT y actualización de estados sin afectar otros roles.
- [x] Pruebas unitarias, API y migración/persistencia en PostgreSQL temporal (23 aprobadas).
- [ ] Desplegar código y migración 039; configurar secreto y activar Cloud Scheduler (`59 23 6 * *`, America/Santiago).
- Guía: [sincronización de conductores](../docs/SINCRONIZACION_CONDUCTORES.md).

## REP-1 — Repuestos utilizados por falla

- [x] Preparar el [plan específico de implementación](PLAN_IMPLEMENTACION_REPUESTOS_POR_FALLA.md) para catálogo y trazabilidad de artículos vinculados a una falla concreta de OT.
- [x] Unificar los heads de Alembic y preparar la migración de repuestos.
- [x] Implementar catálogo vacío, registro/anulación de uso, permisos y pruebas; sin importación Excel.

Alcance acordado: identificar el repuesto utilizado, la cantidad declarada, la falla, el autor y la fecha; OT y bus se derivan de relaciones existentes. La cantidad es informativa, sin control de stock ni bodegas; el catálogo incluye precio neto e IVA informativos. La implementación local y sus contratos se describen en la guía de repuestos. Las migraciones aún deben aplicarse al entorno correspondiente.

## DASH-1 — Dashboard de consulta bajo demanda

Implementación local en `feature/dashboard`: estructura modular, consultas SQL, autorización, DTOs, pruebas y contratos frontend. No se programó el corte diario de las 08:00: la decisión final es recalcular en cada consulta sin guardar resultados. El consumidor frontend debe reemplazar la carga de JSON por la API; ese trabajo y la publicación quedan fuera de esta entrega. Evidencias de validación en AV-0132 y [guía de integración](GUIA_FRONTEND_DASHBOARD.md).

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

## Fase 10: Visibilidad de Órdenes en Reparación y Pendientes en Bandeja del Mecánico (MANT-10)
- [x] Actualización de la consulta CTE de alto rendimiento y fallback SQLite en `list_pendientes` y `count_pendientes` (`TallerRepository`) para incluir órdenes en estado `PENDIENTE` y `EN_REPARACION`.
- [x] Erradicación de la consulta sobre el estado obsoleto `REPORTADO` (unificado a `PENDIENTE` desde migración 014).
- [x] Soporte de parámetro opcional de consulta `estado` en `GET /api/v1/taller/pendientes` permitiendo filtrado específico a futuro si se requiere (`?estado=PENDIENTE` o `?estado=EN_REPARACION`).
- [x] Propagación del parámetro `estado` y rangos de fechas a través de `SolicitudService` y `TallerService`.
- [x] Actualización de `seed.py` para sembrar órdenes de prueba directamente en estado `PENDIENTE`.
- [x] Cobertura de pruebas completa en `tests/unit/test_pendientes_en_reparacion.py` (3 tests unitarios y de integración de endpoint REST).
- [x] Suite completa de pruebas automatizadas ejecutada y aprobada (203/203 tests verdes).

## Fase 11: Depuración de Fallas e Imágenes por Supervisión (MANT-11)
- [x] DTO `EditarFallaDTO` para modificación controlada de averías con justificación obligatoria.
- [x] Repositorio atómico `delete_detalle_con_dependencias` con orden de cascada segura (colaboradores -> ubicaciones -> eventos mecánicos -> eventos falla -> asignaciones -> desasociación evidencias -> detalle).
- [x] Endpoint `DELETE /api/v1/supervision/solicitudes/{id}/detalles/{detalle_id}`: eliminación en 1 clic de falla duplicada con bitácora inmutable `"Se elimina falla '{falla}' por duplicidad"`, desasociando evidencias y desactivando presencias de mecánicos sin fallas activas.
- [x] Endpoint `PATCH /api/v1/supervision/solicitudes/{id}/detalles/{detalle_id}`: edición con justificación obligatoria estampada en bitácora inmutable `"Avería #{detalle_id} modificada: de '{ant}' a '{nuevo}'. Justificación: {just}"`.
- [x] Endpoint `DELETE /api/v1/supervision/solicitudes/{id}/evidencias/{evidencia_id}`: borrado físico y relacional de fotos iniciales del chofer con 1 clic, reajuste automático de foto de portada (`foto_url`) y bitácora `"Se elimina una imagen de la orden de trabajo"`.
- [x] Protección de evidencias de bitácora y resoluciones de averías contra eliminación no permitida.
- [x] Cobertura completa de 6 tests unitarios en `tests/unit/test_supervision_depuracion_fallas_y_fotos.py` (100% aprobados).





## Revisión individual de fallas (2026-11-09)

Implementados `estado_revision`, `revisado_por_id` y `fecha_revision`, aprobación individual por supervisión y aprobación de fallas seleccionadas al asignarse. Reportar sin asignación previa ni autoasignación deja revisión pendiente. Migración 041 preparada, pendiente de aplicar al entorno de despliegue. Contrato y reglas: [Revisión individual de fallas](../docs/REVISION_INDIVIDUAL_FALLAS.md).


## Revisión completa de repuestos (2026-11-09)

Verificados 42 casos de repuestos y 120 de regresión relacionada, sin fallos finales. Migración 038 y concurrencia verificadas en PostgreSQL temporal, sin diferencias entre sus tablas y los modelos. Corregidos edición con ID cero, consistencia UTC, validación de rol actual y aprobación de fallas en la conversión inicial a OT, manteniendo el alcance selectivo al asignarse. No se aplicaron migraciones a bases externas. Evidencias y límites: [Informe de revisión](../docs/REVISION_REPUESTOS_20261109.md).


Guía de integración pendiente en frontend: [Revisión individual de fallas](GUIA_FRONTEND_REVISION_FALLAS.md), con contrato, aprobación selectiva, permisos, manejo de caché y checklist de aceptación. Documentada el 2026-11-09.


### Permanencia física en taller — 2026-11-10

Auditoría expone tiempo_taller, horas_en_taller y horas_taller_acumuladas con suma de visitas físicas y congelación de OTs cerradas. La ficha de bus incluye horas_taller_totales agregado en SQL sobre todas sus OTs. Sin migraciones. Contrato: docs/HORAS_REALES_TALLER.md. Verificación: 61 pruebas aprobadas.


### Temporizador interno de conductores — 2026-11-11

Sincronización mensual dentro del lifespan FastAPI en production, habilitada por defecto con CONDUCTORES_SYNC_TIMER_ENABLED. Comprueba cada 60 s, recupera el último período vencido al iniciar y reintenta errores a los 300 s. Reutiliza lock y deduplicación mensual PostgreSQL. Sin Cloud Scheduler ni GitHub Actions; el secreto HTTP no es necesario para el timer. Cloud Run requiere una instancia activa y CPU disponible para trabajar sin tráfico. 32 pruebas aprobadas. Detalle: docs/SINCRONIZACION_CONDUCTORES.md.
