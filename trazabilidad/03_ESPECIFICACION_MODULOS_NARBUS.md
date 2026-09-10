# Especificación de Módulos y Arquitectura Narbus Taller

> **Versión:** 3.0.0  
> **Fecha:** 2026-09-09  
> **Total Endpoints:** 43 endpoints RESTful activos  
> **Arquitectura:** Clean Architecture en 3 capas (Router $\rightarrow$ Service $\rightarrow$ Repository) + Storage Provider (GCS / Local)

---

## 1. Módulo Autenticación y Usuarios (`/api/v1/auth`)
- `POST /login`: Autenticación vía payload JSON (`LoginDTO`). Retorna JWT Bearer y datos del usuario.
- `POST /login/token`: Autenticación compatible con OAuth2 Password Request Form (`username`, `password`).
- `GET /me`: Consulta de perfil del usuario logueado (`UsuarioResponseDTO`).
- `GET /usuarios`: Listado de usuarios activos (requiere supervisor o admin).
- `POST /usuarios`: Creación administrativa de nuevos usuarios con rol específico.
- `DELETE /usuarios/{id}`: Soft delete (desactivación lógica).
- `GET /usuarios/buscar-mecanicos`: Búsqueda y autocompletado por nombre de mecánicos activos para asignación colaborativa.

---

## 2. Módulo Buses (`/api/v1/buses`)
- `GET /`: Catálogo de buses. Filtros: `solo_activos=true`, `solo_flota_taller=true` (`200 <= n_bus < 900`).
- `GET /buscar`: Búsqueda rápida optimizada por prefijo/número. Retorna `List[BusSimpleDTO]` (`id`, `n_bus`, `patente`, `en_taller`).
- `GET /{id}`: Detalle de un bus por su ID primario.
- `GET /numero/{n_bus}`: Detalle de un bus por su número de máquina (ej. `"330"`).
- `PATCH /{id}/en-taller`: Actualización directa con `RETURNING` del flag físico `en_taller: bool`.

---

## 3. Módulo Mantención Taller (`/api/v1/mantencion`)

### Catálogos y Creación
- `GET /pauta/items`: Catálogo maestro de los 11 ítems de inspección preventiva categorizados (`Cache-Control: max-age=300`).
- `GET /categorias`: Catálogo de categorías de falla con `falla_id` y `falla_nombre` precalculados (`Cache-Control: max-age=300`).
- `GET /fallas`: Maestro de fallas preconcebidas con filtro opcional por `categoria_id`.
- `POST /solicitudes`: Creación de orden de taller. Soporta `multipart/form-data` con campo binario `foto` (subida atómica a GCS en 1 solo request HTTP) o `application/json` con `foto_url`.

### Bandejas de Trabajo del Mecánico (Single-Roundtrip SQL)
- `GET /pendientes`: Pestaña 1 mecánico (buses esperando en taller, paginación con `limit` y `skip`, `Cache-Control: max-age=15`).
- `GET /mis-trabajos`: Pestaña 2 mecánico (órdenes en reparación donde el mecánico está asignado activamente, `limit` y `skip`).
- `GET /{id}`: Consulta detallada de la solicitud con todas sus relaciones cargadas.

### Operaciones y Asignaciones Atómicas
- `POST /{id}/autoasignar`: Auto-asignación a fallas específicas con soporte de colaboradores (`colaboradores_ids`) y co-responsabilidad atómica.
- `POST /{id}/asignar`: Asignación realizada por supervisora a un mecánico específico.
- `POST /{id}/tomar`: Auto-asignación de bus + invitación a colaboradores + comentario inicial opcional.
- `POST /{id}/desasignarme`: Desasignación individual de mecánico sin afectar a los demás co-responsables.
- `POST /{id}/liberar-turno`: Entrega de turno de la cuadrilla completa, pasando la orden a `PENDIENTE_REASIGNACION`.
- `POST /{id}/terminar-avance`: Cierre de avance del mecánico calculando automáticamente la duración en minutos (`duracion_minutos`).
- `POST /{id}/agregar-falla`: El mecánico agrega una falla detectada en taller durante la inspección.
- `POST /{id}/agregar-colaborador`: El mecánico invita a un compañero a colaborar en la solicitud.

### Mutaciones Atómicas de Alta Frecuencia (Nivel 3 - DTOs Ultrarrápidos)
- `PATCH /{id}/detalles/{detalle_id}/check`: Marca/desmarca falla como resuelta. Retorna `DetalleUpdateDTO` (~290ms).
- `PATCH /{id}/detalles/{detalle_id}/repuesto`: Reporta o retira bloqueo por falta de repuestos. Retorna `DetalleUpdateDTO`.
- `POST /{id}/comentarios`: Registro de nota en la bitácora auditable. Retorna `ComentarioAddedDTO`.

### Pauta Preventiva y Cierre
- `GET /{id}/pauta`: Consulta el estado y progreso de la pauta preventiva de la orden.
- `POST /{id}/pauta`: Registro y actualización batch de respuestas a la pauta preventiva en 1 sola transacción.
- `POST /{id}/liberar`: Finaliza los trabajos, exige justificaciones condicionales de pauta incompleta o cierre parcial, y libera el bus (`en_taller = false`).
- `POST /{id}/finalizar`: Alias de cierre operacional de la orden.

---

## 4. Módulo Neumáticos (`/api/v1/neumaticos` y alias)
- `GET /formularioNeumatico`: Consulta de estado y schema del formulario.
- `POST /formularioNeumatico`: Envío de reporte multipart (`maquina`, `tipo_bus`, `ruedas`, `motivo`, `precio`, `marca_fuego`, `evidencia`). Sube la evidencia a GCS y persiste `evidencia_url`.
- `GET /reportes`: Listado de reportes de neumáticos registrados.
- `GET /reportes/{id}`: Detalle de un reporte específico.
- `POST /reportes`: Endpoint RESTful canónico para registro de reportes.

---

## 5. Módulo Supervisión y Telemetría (`/api/v1/supervision`)
- `GET /resumen-taller`: Dashboard ejecutivo con KPIs, conteos por estado, desglose por categoría y alertas en 1 sola consulta CTE.
- `GET /alertas`: Feed en tiempo real de alertas operacionales (`REPUESTO_FALTANTE`, `DEFECTO_PAUTA`, `BUS_SIN_MECANICOS`).
- `GET /buses/taller`: Paginación y auditoría detallada de buses en taller con filtros por estado (`estado`) y búsqueda (`q`).
- `GET /auditoria/buses-taller`: Auditoría analítica consolidada de trazabilidad histórica.

---

## 6. Almacenamiento Cloud de Imágenes (`app/core/storage`)
- **Arquitectura:** Patrón Provider (`BaseStorageProvider`, `GCSStorageProvider`, `LocalStorageProvider`).
- **Google Cloud Storage (GCS):** Sube objetos a Google Cloud con Application Default Credentials (ADC) en producción o Service Account JSON en local.
- **Operación Servidor a Servidor:** I/O asíncrono no bloqueante con `asyncio.to_thread`.
- **Modo Local:** Fallback automático a `./uploads/` cuando `STORAGE_PROVIDER=local`.
- **Cero Cuellos de Botella:** Procesamiento en 1 solo request HTTP multipart en los endpoints de negocio sin endpoints previos de upload.
