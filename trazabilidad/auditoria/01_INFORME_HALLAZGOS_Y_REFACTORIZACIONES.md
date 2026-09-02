# Informe Técnico de Auditoría de Código y Refactorizaciones Backend

**Fecha de Auditoría:** 2026-09-02  
**Repositorio:** `BackendTallerNarbus`  
**Entorno:** `dev_local` (Python 3.12, FastAPI, SQLAlchemy 2.0 Async, Alembic, PostgreSQL)  
**Clasificación:** Trazabilidad de Deuda Técnica y Calidad de Software

---

## 1. Resumen Ejecutivo

Se realizó una inspección estática y dinámica del código fuente del backend para identificar deudas técnicas, violaciones de patrones de diseño, vulnerabilidades de seguridad, cuellos de botella de rendimiento y malas prácticas en el uso de FastAPI, SQLAlchemy Async y Pydantic V2.

Se categorizaron **12 hallazgos clave**, estructurados en 4 niveles de severidad: **Crítica (3)**, **Alta (4)**, **Media (3)** y **Baja (2)**.

---

## 2. Matriz de Priorización de Hallazgos

| ID | Hallazgo | Severidad | Impacto | Módulos / Archivos Afectados |
|---|---|---|---|---|
| **CRIT-01** | Parches DDL en tiempo de ejecución (`db_patch.py`) vs Alembic | 🔴 **Crítica** | Integridad y estabilidad del esquema de BD en producción | `app/core/db_patch.py`, `app/main.py`, `alembic/` |
| **CRIT-02** | Cómputo analítico en memoria (Full Table Fetch) en Supervisión | 🔴 **Crítica** | Riesgo inminente de Out-of-Memory (OOM) y latencia desmedida | `app/modules/supervision/services/supervision_service.py`, `supervision_repository.py` |
| **CRIT-03** | `db.commit()` ejecutado dentro de Repositorios (Unit of Work roto) | 🔴 **Crítica** | Pérdida de atomicidad y riesgo de corrupción en transacciones multi-paso | `app/modules/mantencion/repository/mantencion_repository.py`, `bus_repository.py` |
| **ALTA-01** | Arquitectura Invertida: Smart Repository / Anemic Service | 🟠 **Alta** | Violación de Clean Architecture, acoplamiento extremo | `app/modules/mantencion/repository/`, `mantencion_service.py`, `app/modules/auth/` |
| **ALTA-02** | Manejo de archivos síncrono/bloqueante sin validación de seguridad | 🟠 **Alta** | Bloqueo del Event Loop de AsyncIO y riesgo de saturación de disco | `app/modules/neumaticos/services/formulario_neumatico_service.py` |
| **ALTA-03** | Endpoint `/health/db` responde HTTP 200 en fallo y expone trazas | 🟠 **Alta** | Falso positivo en monitoreo de infraestructura y fuga de datos internos | `app/api/v1/endpoints/health.py` |
| **ALTA-04** | Consultas N+1 y filtrado en memoria de buses en repositorios | 🟠 **Alta** | Sobrecarga de red y uso ineficiente del motor relacional | `app/modules/buses/repository/bus_repository.py`, `user_repository.py` |
| **MED-01** | Endpoints de Neumáticos fuera de estándar REST y sin autenticación | 🟡 **Media** | Vulnerabilidad de acceso anónimo e inconsistencia de API | `app/modules/neumaticos/api/router.py`, `reporte_neumatico_dto.py` |
| **MED-02** | Código muerto y artefactos huérfanos | 🟡 **Media** | Confusión de mantenimiento y complejidad innecesaria | `formulario_mantencion_service.py`, `taller_solicitud_repository.py`, `conductores/` |
| **MED-03** | Lanzamiento directo de `HTTPException` en lugar de Excepciones de Dominio | 🟡 **Media** | Violación del estándar de excepciones del proyecto | `app/api/deps.py`, `app/modules/auth/api/router.py` |
| **BAJA-01** | Boilerplate excesivo en mapeo manual DTO (`_to_solicitud_dto`) | 🟢 **Baja** | Mantenibilidad deficiente y duplicación de concatenaciones | `app/modules/mantencion/services/mantencion_service.py`, `usuario.py` |
| **BAJA-02** | Configuración incompleta en `pytest.ini` para ejecución CLI | 🟢 **Baja** | Falla al ejecutar `pytest` directamente sin `python -m` | `pytest.ini` |

---

## 3. Detalle Exhaustivo de los Hallazgos

### 3.1. CRIT-01: Parches DDL en tiempo de ejecución (`db_patch.py`) vs Alembic
* **Descripción:** En `app/main.py` (`lifespan`), se ejecuta `apply_db_patches()`. Dicha función ejecuta sentencias `ALTER TABLE ADD COLUMN IF NOT EXISTS` y `CREATE TABLE IF NOT EXISTS` de forma directa contra la base de datos viva.
* **Justificación técnica del riesgo:**
  1. En un despliegue con múltiples réplicas (Docker, Kubernetes o Uvicorn con múltiples workers), todos intentan modificar el catálogo concurrente de PostgreSQL al inicio, provocando contención y bloqueos (`AccessExclusiveLock`).
  2. Bypassea el historial de migraciones de Alembic, imposibilitando reproducir el esquema en staging/producción de forma determinista o realizar rollbacks (`alembic downgrade`).
  3. Los errores se capturan con un genérico `except Exception: pass` que silencia fallas estructurales.
* **Solución requerida:** Consolidar las sentencias en una migración formal de Alembic (`006_consolidacion_esquema_taller.py`), registrar todos los modelos en `app/models/__init__.py` y eliminar `db_patch.py`.

### 3.2. CRIT-02: Cómputo analítico en memoria (Full Table Fetch) en Supervisión
* **Descripción:** `SupervisionService.get_resumen_taller` invoca `supervision_repository.get_auditoria(db)` sin filtros ni límites. Trae el 100% del historial de órdenes de mantención, cargando 11 relaciones anidadas por registro (`selectinload`), y calcula en Python conteos por estado, fallas resueltas y alertas mediante bucles `for` y `sum()`.
* **Justificación técnica del riesgo:**
  1. Al crecer el volumen de datos (1.000+ solicitudes con 5 fallas y 19 respuestas de pauta cada una), el tamaño del payload en RAM supera los gigabytes, colapsando el proceso por OOM (Out Of Memory).
  2. Latencia inaceptable para un panel de supervisión (decenas de segundos en una simple consulta de dashboard).
* **Solución requerida:** Reescribir `supervision_repository` para calcular métricas mediante agregaciones SQL nativas (`GROUP BY estado`, `COUNT(*)`, `SUM(CASE WHEN...)`) y restringir la búsqueda de alertas exclusivamente a órdenes activas (`estado != 'FINALIZADO'`).

### 3.3. CRIT-03: `db.commit()` ejecutado dentro de Repositorios (Unit of Work roto)
* **Descripción:** Casi todos los métodos de escritura en `MantencionRepository`, `BusRepository` y `UserRepository` ejecutan `await db.commit()` de forma autónoma.
* **Justificación técnica del riesgo:**
  1. En Clean Architecture, el repositorio gestiona colecciones de entidades, mientras que la transacción (Unit of Work) es orquestada por el Caso de Uso / Servicio.
  2. Si una operación requiere pasos atómicos (ej. marcar bus como desocupado + cerrar solicitud + generar bitácora), y el paso 3 falla después de que el paso 1 y 2 hicieron `commit()`, la base de datos queda corrupta e inconsistente sin posibilidad de `rollback`.
* **Solución requerida:** Sustituir `await db.commit()` dentro de los repositorios por `await db.flush()`. El `commit()` final debe controlarse explícitamente en el servicio o mediante un middleware/context manager transaccional.

### 3.4. ALTA-01: Arquitectura Invertida: Smart Repository / Anemic Service
* **Descripción:** `MantencionRepository` concentra más de 1.000 líneas con validaciones de negocio (`BusinessRuleException`), cálculo de tiempos de turno, mutaciones del estado de buses y generación de comentarios de bitácora. `MantencionService` es un mero pasamanos. En contraste, `auth` no tiene servicio alguno (el router llama directo al repositorio).
* **Justificación técnica del riesgo:**
  1. Dificulta las pruebas unitarias: es imposible testear la lógica de negocio sin levantar una base de datos.
  2. Viola el principio de Responsabilidad Única (SRP).
* **Solución requerida:** Trasladar todas las reglas de negocio a `MantencionService` y crear `AuthService` para aislar el router de la persistencia.

### 3.5. ALTA-02: Manejo de archivos síncrono/bloqueante sin validación de seguridad
* **Descripción:** `formulario_neumatico_service.py` lee y escribe archivos usando `with open(ruta, "wb") as f: f.write(contenido)` dentro de corrutinas asíncronas, sin límite de peso, sin comprobación de cabeceras mágicas (MIME type real) y tomando extensiones crudas.
* **Justificación técnica del riesgo:**
  1. I/O de disco bloqueante en el hilo principal del Event Loop: mientras se guarda un archivo grande, FastAPI se congela para todas las demás peticiones entrantes.
  2. Vulnerabilidad de DoS (Denial of Service) por saturación de disco al permitir archivos ilimitados.
* **Solución requerida:** Usar `aiofiles` o `asyncio.to_thread` para I/O asíncrono, fijar tamaño máximo (ej. 5MB) y validar tipos MIME reales con lista blanca estricta (`image/jpeg`, `image/png`, `image/webp`).

### 3.6. ALTA-03: Endpoint `/health/db` responde HTTP 200 en fallo y expone trazas
* **Descripción:** `GET /health/db` captura cualquier fallo de conexión y devuelve `{"status": "unhealthy", "database": str(e)}` con código de estado 200 OK.
* **Justificación técnica del riesgo:**
  1. Los balanceadores de carga y sondas (Kubernetes, AWS ALB) consideran 200 como sistema saludable, impidiendo el reinicio automático del pod ante una desconexión de BD.
  2. `str(e)` expone hosts, puertos, credenciales o nombres de base de datos a clientes externos.
* **Solución requerida:** Retornar `status.HTTP_503_SERVICE_UNAVAILABLE` y omitir detalles internos.

### 3.7. ALTA-04: Consultas N+1 y filtrado en memoria de buses en repositorios
* **Descripción:**
  * `BusRepository.buscar_n_buses_por_prefijo`: extrae todos los buses a Python y los filtra con `str.startswith()` y ordenamiento en Python.
  * `UserRepository.get_mecanicos_by_nombres_o_usernames`: ejecuta una consulta SQL por cada iteración del bucle `for`.
* **Justificación técnica del riesgo:** Desperdicio de CPU y latencia evitable.
* **Solución requerida:** Utilizar `Bus.n_bus.like(f"{clean_prefix}%")` y operadores SQL `IN` / `or_` combinados.

### 3.8. MED-01: Endpoints de Neumáticos fuera de estándar REST y sin autenticación
* **Descripción:** Ruta `/formularioNeumatico` en camelCase, endpoint GET dummy con `data: None`, POST sin `require_current_user` y sin usar `ReporteNeumaticoResponseDTO`.
* **Solución requerida:** Renombrar a `/neumaticos/reportes`, agregar autenticación estricta y DTOs de salida.

### 3.9. MED-02: Código muerto y artefactos huérfanos
* **Descripción:** Archivos deprecados (`formulario_mantencion_service.py`, `taller_solicitud_repository.py`, `taller_solicitud_dto.py`, módulo `conductores`).
* **Solución requerida:** Depuración limpia de archivos obsoletos.

### 3.10. MED-03: Uso de `HTTPException` directa vs Excepciones de Dominio
* **Descripción:** Uso de `HTTPException` en `deps.py` y `auth/router.py`.
* **Solución requerida:** Implementar `AuthenticationException` (401) y usar `PermissionException` (403) unificadas en `app/core/exceptions.py`.

### 3.11. BAJA-01: Boilerplate excesivo en mapeo manual DTO (`_to_solicitud_dto`)
* **Descripción:** 140 líneas de mapeo artesanal ignorando `usuario.nombre_completo` y `model_validate`.
* **Solución requerida:** Aprovechar Pydantic V2 `from_attributes=True` y propiedades de modelo.

### 3.12. BAJA-02: Configuración incompleta en `pytest.ini`
* **Descripción:** Falta `pythonpath = .`, impidiendo correr `pytest` directamente.
* **Solución requerida:** Añadir `pythonpath = .` a `pytest.ini`.

---

## 4. Estado y Próximos Pasos

Este documento sirve como base oficial para el plan de refactorización y aseguramiento de calidad del backend.
