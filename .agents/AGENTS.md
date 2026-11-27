# Reglas, Arquitectura y Subagentes AI (.agents/AGENTS.md)

> Sincronizado con el orquestador raíz [AGENTS.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/AGENTS.md). Este directorio `.agents/` centraliza tanto las **reglas y guías técnicas canónicas** del repositorio como las definiciones de los **subagentes especializados** en `.agents/agents/<nombre-agente>/agent.md`.

## 0. Enfoque Exclusivo Backend y Mapa de `.agents/`
- **Repositorio Backend Autónomo:** Este repositorio es exclusivamente de **Backend API** (`BackendTallerNarbus`). El Frontend (`FrontendTallerNarbus` / `ProtoNeumaticos`) se maneja en un repositorio completamente separado e interactúa únicamente vía REST (`/api/v1/*`) y WebSockets (`app/core/realtime/`).
- **Sin Interferencia de Frontend:** Todos los diseños, especificaciones, avances y planes corresponden 100% a endpoints, modelos de datos, servicios, repositorios y reglas de negocio del Backend.
- **Estructura del Directorio `.agents/`:**
  - `.agents/AGENTS.md`: Reglas globales operativas, flujo de trazabilidad y catálogo de subagentes.
  - [.agents/BUENAS_PRACTICAS_Y_ESTANDARES_BACKEND.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_Y_ESTANDARES_BACKEND.md): Arquitectura de 4 capas, transacciones, SQL, I/O asíncrono, seguridad y REST.
  - [.agents/BUENAS_PRACTICAS_BD.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_BD.md): Diseño relacional 3NF, SQLAlchemy 2.0 (`Mapped`/`mapped_column`) y migraciones Alembic.
  - [.agents/BUENAS_PRACTICAS_CODIGO.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_CODIGO.md): Principios SOLID, SRP (5-20 líneas), CQS, Fail-Fast, testing AAA y Conventional Commits.
  - `.agents/agents/<nombre-agente>/agent.md`: Subagentes especializados descubiertos automáticamente por Antigravity.

## 0.1 Catálogo y Enrutamiento de Subagentes (`.agents/agents/`)
El agente principal y el **Orchestrator** deben delegar el trabajo especializado mediante `invoke_subagent` respetando la división por costo/capacidad de razonamiento:

| Subagente (`name`) | Definición | `model` | Responsabilidad y Disparadores de Delegación | Guías Obligatorias |
| :--- | :--- | :---: | :--- | :--- |
| **`arquitecto-dominio-seguridad`** | [agent.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/agents/arquitecto-dominio-seguridad/agent.md) | `pro` | Diseño/refactorización multi-módulo; invariantes de OT, cierre de cuadrilla, presencia, estadías y bitácora inmutable; JWT, RBAC, rol `VISUAL` (solo lectura), CORS y GCS Signed URLs; debugging de concurrencia, timers (WhatsApp/Telegram/conductores) y WebSockets. | `BUENAS_PRACTICAS_Y_ESTANDARES_BACKEND.md`, `BUENAS_PRACTICAS_CODIGO.md` |
| **`especialista-datos-rendimiento`** | [agent.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/agents/especialista-datos-rendimiento/agent.md) | `pro` | Modelado 3NF en SQLAlchemy 2.0 (`app/models/__init__.py`); migraciones Alembic de riesgo medio/alto (`NOT NULL` en 3 fases, renombrados, backfills, merge de heads); CTEs SQL (`dashboard`, `supervision`) y presupuesto `X-DB-Round-Trips`. | `BUENAS_PRACTICAS_BD.md`, `BUENAS_PRACTICAS_Y_ESTANDARES_BACKEND.md` |
| **`implementador-api-fastapi`** | [agent.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/agents/implementador-api-fastapi/agent.md) | `flash` | Implementación ágil de Routers, Services, Repositories y DTOs Pydantic v2 sobre diseño claro; filtros y paginación (`skip`, `limit`, `X-Total-Count`); refactorizaciones acotadas de Clean Code y excepciones de dominio. | `BUENAS_PRACTICAS_Y_ESTANDARES_BACKEND.md`, `BUENAS_PRACTICAS_CODIGO.md` |
| **`ingeniero-qa-migraciones`** | [agent.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/agents/ingeniero-qa-migraciones/agent.md) | `flash` | Creación y ejecución de pruebas unitarias AAA (`AsyncMock` en `tests/unit/`), integración ASGI (`httpx` + `aiosqlite` en `tests/integration/`) y E2E; validación local del ciclo completo de Alembic (`upgrade` -> `downgrade -1` -> `upgrade` -> `check`). | `BUENAS_PRACTICAS_CODIGO.md` (Sec. 9), `BUENAS_PRACTICAS_BD.md` (Sec. 3 y 7) |
| **`documentador-trazabilidad-contratos`** | [agent.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/agents/documentador-trazabilidad-contratos/agent.md) | `flash` | Exploración rápida de endpoints/DTOs; redacción de contratos para frontend (`GUIA_FRONTEND_*.md`, `trazabilidad/05_*`, `06_*`, `docs/*.md`); avances secuenciales JSON en `trazabilidad/avances/` y estado en `01_ESTADO_ACTUAL_PROYECTO.md`. | `.agents/AGENTS.md` (Sec. 0 y 4) |

- **Flujo multi-agente recomendado:** (1) Diseño/Esquema con `arquitecto-dominio-seguridad` y/o `especialista-datos-rendimiento` (`pro`) → (2) Codificación de capas con `implementador-api-fastapi` (`flash`, usando `Workspace: "share"` si hay edición paralela de módulos independientes) → (3) Verificación y cierre en paralelo con `ingeniero-qa-migraciones` y `documentador-trazabilidad-contratos` (`flash`).

## 1. Entorno de Ejecución Local y Base de Datos
- **Entorno Local Estricto:** Toda la ejecución, desarrollo y pruebas se realizan de forma **local** (`dev_local`, `python run.py --local`).
- **Restricción de Base de Datos:** Solo se permite el uso de consultas de lectura (**GET / SELECT**) a la base de datos de manera directa para operaciones de verificación. Todas las modificaciones estructurales o de datos deben realizarse mediante código o migraciones de Alembic.
- **Estándares y Migraciones de BD:** Seguir obligatoriamente las directrices de diseño relacional, modelos con SQLAlchemy 2.0 y ciclo de vida de migraciones documentadas en [.agents/BUENAS_PRACTICAS_BD.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_BD.md) (delegando diseño complejo a `especialista-datos-rendimiento` y verificación del ciclo a `ingeniero-qa-migraciones`).

## 2. Arquitectura Backend, DTOs y Excepciones de Dominio
- **Separación Estricta de Capas (4 Capas):** Respetar la arquitectura Router -> Service -> Repository -> DTO definida en [.agents/BUENAS_PRACTICAS_Y_ESTANDARES_BACKEND.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_Y_ESTANDARES_BACKEND.md) (supervisada por `arquitecto-dominio-seguridad` e implementada por `implementador-api-fastapi`).
- **Uso Obligatorio de DTOs (Pydantic Models):**
  - Todo endpoint, entrada de datos (`payload`/`request body`) o respuesta (`response_model`) debe contar con su correspondiente **DTO (Data Transfer Object)** definido en la carpeta `dtos/` del módulo respectivo.
  - No se deben exponer directamente los modelos ORM de SQLAlchemy en los controladores.
- **Uso Obligatorio de Excepciones de Dominio:** El proyecto cuenta con un sistema centralizado de excepciones en `app/core/exceptions.py`.
- **Regla en Nuevas Funcionalidades:** Toda nueva mejora, endpoint, servicio o repositorio DEBE utilizar las excepciones de dominio existentes (`NotFoundException`, `BusinessRuleException`, `ConflictException`, `PermissionException`, `AuthenticationException`), evitando lanzar `ValueError` o `HTTPException` en servicios o usar bloques `try/except` repetitivos en los routers.
- **RBAC y Rol `VISUAL`:** Proteger rutas mutantes con dependencias de `app/api/deps.py` respetando `enforce_visual_read_only` (escrituras bloqueadas con 403 para `VISUAL`) y el presupuesto de viajes `X-DB-Round-Trips` en `/api/v1/taller/*`.

## 3. Código Limpio, Principios SOLID y Testing
- **Estándares de Código Limpio y Principios SOLID:** Seguir de forma obligatoria las directrices de [.agents/BUENAS_PRACTICAS_CODIGO.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_CODIGO.md), asegurando cumplimiento de SRP (funciones coordinadoras vs ejecutoras, longitud entre 5 y 20 líneas), pocos parámetros (0 a 2), Command-Query Separation (CQS), ausencia de boolean flags como parámetros, nomenclatura semántica, números mágicos aislados en constantes y enfoque "Fail Fast" con guard clauses.
- **Estrategia de Testing:** Toda lógica de negocio no trivial debe contar con pruebas unitarias estructuradas bajo el patrón **Arrange-Act-Assert (AAA)** y aislamiento de persistencia mediante mocks (`AsyncMock`), ejecutadas y validadas mediante `ingeniero-qa-migraciones`.

## 4. Trazabilidad del Proyecto (Full Backend)
- **Subagente Responsable:** Delegar la actualización de contratos REST/WebSocket, barridos de estado y generación de archivos de avance a `documentador-trazabilidad-contratos`.
- **Estructura de la Carpeta `trazabilidad/`:**
  - `trazabilidad/avances/`: Contiene archivos JSON numerados secuencialmente registrando cada avance significativo del backend (ej. `0001_YYYYMMDDTHHMMSSZ_descripcion.json`).
  - `01_ESTADO_ACTUAL_PROYECTO.md`: Documento vivo con el estado general de los módulos y endpoints.
  - `02_CONTENIDO_Y_ALCANZABLE_BACKEND.md`: Especificación técnica del alcance del backend.
  - `03_ESPECIFICACION_MODULOS_NARBUS.md`: Detalle de contratos REST, DTOs y reglas de negocio.
  - `04_PLAN_IMPLEMENTACION_BACKEND.md`: Plan global de desarrollo del Backend.
  - `05_CONTRATOS_API_FRONTEND.md` / `06_CATALOGO_ENDPOINTS_PAYLOADS_RESPUESTAS.md` / `GUIA_FRONTEND_*.md`: Contratos de integración para `FrontendTallerNarbus`.
- **Registro JSON de Avances Obligatorio (Incluyendo Decisiones Técnicas):** Cada registro de avance en `trazabilidad/avances/` debe incluir de manera **obligatoria** el apartado de `decisions` donde se fundamenten las decisiones tomadas durante la tarea.
  
  Estructura JSON estándar:
  ```json
  {
    "schemaVersion": "1.0",
    "sequence": 1,
    "id": "AV-0001",
    "timestamp": "2026-08-28T08:54:22Z",
    "phase": "backend_taller",
    "milestone": { "id": "MANT-1", "name": "Nombre Hito", "statusBefore": "in_progress", "statusAfter": "completed" },
    "type": "completed",
    "summary": "Resumen detallado de la tarea de backend completada.",
    "scope": {
      "planned": ["Items planeados..."],
      "completed": ["Items completados..."],
      "pending": ["Items pendientes..."],
      "outOfScope": ["Fuera de alcance..."]
    },
    "changes": [{ "path": "ruta/al/archivo", "action": "created|modified|deleted", "summary": "Descripción del cambio" }],
    "decisions": [
      {
        "id": "DEC-001",
        "title": "Título de la decisión técnica tomada",
        "rationale": "Justificación y motivo técnico de la decisión",
        "consequences": "Efecto o beneficio en la arquitectura del backend"
      }
    ],
    "verification": [{ "command": "Comando de prueba", "result": "passed|failed|not_run", "evidence": "Detalle/Salida de la prueba" }],
    "blockers": [],
    "nextStep": "Siguiente paso a realizar en el backend.",
    "git": { "repository": "BackendTallerNarbus", "branch": "develop", "commit": "hash", "dirty": false },
    "notes": ["Notas adicionales..."]
  }
  ```
- **Resumen del Día / Estado:** Cuando el usuario solicite un resumen o estado del proyecto, se revisará la carpeta `trazabilidad/` y sus registros de avances para generar un reporte preciso enfocado 100% en el backend.

## 5. Logging y Observabilidad
- **Uso de Logger:** Se debe implementar logging utilizando el módulo estándar de Python (`logging.getLogger(__name__)`) siempre que sea necesario en servicios, repositorios, middleware y exception handlers.
- **Trazabilidad de Eventos:** Registrar información relevante (eventos críticos, fallos, cambios de estado o excepciones no controladas) para asegurar observabilidad en el backend.
- **Prohibición de print:** NUNCA utilizar `print()` en ninguna parte del código backend.

## 6. Metodología GitFlow y Commits
- **Flujo de Ramas:** El desarrollo se realiza en ramas `feature/*` que se integran a `develop` mediante la estrategia de GitFlow.
- **Prohibido Merge Directo a Main:** NUNCA se realiza merge directo de ramas de características (`feature/*`) hacia la rama `main`.
- **Estándar de Commits (Conventional Commits):** Cada commit debe ser atómico y utilizar la convención de Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `perf:`). Está estrictamente prohibido mezclar refactorizaciones y nuevas características en el mismo commit.

