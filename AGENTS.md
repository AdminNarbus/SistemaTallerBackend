# Orquestación de Agentes y Reglas Globales — BackendTallerNarbus

## 1. Contexto del Repositorio
**`BackendTallerNarbus`** es el servidor **Backend API autónomo** encargado de gestionar de principio a fin la operación de mantenimiento mecánico, órdenes de trabajo (OT), cuadrillas, control de patio/estadías, pautas preventivas, repuestos, emergencias de neumáticos, analítica de dashboard y alertas (Meta WhatsApp / Telegram) de la flota de buses de Narbus.

- **Stack Principal**: Python 3.12 (`venv`), FastAPI `>=0.115`, SQLAlchemy `2.0` Async (`asyncpg` + `psycopg2-binary`), PostgreSQL (`dev_local`) / Neon Serverless Postgres, Alembic, Pydantic v2, WebSockets en tiempo real (`app/core/realtime/`) y Google Cloud Storage / almacenamiento local (`app/core/storage/`).
- **Frontera Estricta Backend-Only**: Este repositorio contiene **exclusivamente el Backend**. El cliente web/móvil (`FrontendTallerNarbus` / `ProtoNeumaticos`) vive en un repositorio independiente y se integra únicamente mediante contratos REST (`/api/v1/*`) y eventos WebSocket. Prohibido escribir código de UI/Frontend aquí.

---

## 2. Tabla de Enrutamiento de Subagentes (`.agents/agents/`)

El agente principal y el **Orchestrator** deben delegar tareas especializadas mediante `invoke_subagent` según la siguiente matriz de capacidad/costo (`pro` = máximo razonamiento; `flash` = ejecución rápida y eficiente):

| Subagente (`TypeName`) | Definición | Tier (`model`) | Cuándo Delegar Automáticamente (Disparadores) | Cuándo NO Delegar |
| :--- | :--- | :---: | :--- | :--- |
| **`arquitecto-dominio-seguridad`** | [.agents/agents/arquitecto-dominio-seguridad/agent.md](.agents/agents/arquitecto-dominio-seguridad/agent.md) | `pro` | Diseño o refactorización multi-módulo; reglas complejas de OT, cierre de cuadrilla, presencia, estadías o bitácora inmutable; seguridad JWT, RBAC, rol `VISUAL` (solo lectura), CORS, validación MIME o Signed URLs de GCS; debugging de concurrencia, timers asíncronos (WhatsApp/Telegram/conductores) o WebSockets. | Cambios CRUD simples de un solo archivo o ajustes cosméticos de DTOs. |
| **`especialista-datos-rendimiento`** | [.agents/agents/especialista-datos-rendimiento/agent.md](.agents/agents/especialista-datos-rendimiento/agent.md) | `pro` | Creación/modificación de modelos SQLAlchemy 2.0 y relaciones 3NF; migraciones Alembic de riesgo medio/alto (`NOT NULL` en 3 fases, renombrados, backfills, merge de heads); optimización de CTEs SQL (`dashboard`, `supervision`), eliminación de N+1 y cumplimiento del presupuesto `X-DB-Round-Trips`. | Ejecución rutinaria de suites de tests sin cambios de esquema ni de consultas complejas. |
| **`implementador-api-fastapi`** | [.agents/agents/implementador-api-fastapi/agent.md](.agents/agents/implementador-api-fastapi/agent.md) | `flash` | Implementación de endpoints FastAPI, servicios, repositorios CRUD y DTOs Pydantic v2 sobre un diseño claro; adición de filtros/paginación (`skip`, `limit`, `X-Total-Count`); refactorizaciones acotadas de Clean Code (SRP, constantes `Final`, tipado y excepciones de dominio). | Decisiones abiertas de arquitectura o rediseño del modelo relacional sin especificación previa. |
| **`ingeniero-qa-migraciones`** | [.agents/agents/ingeniero-qa-migraciones/agent.md](.agents/agents/ingeniero-qa-migraciones/agent.md) | `flash` | Creación y reparación de tests unitarios AAA (`AsyncMock` en `tests/unit/`), integración ASGI (`httpx` + `aiosqlite` en `tests/integration/`) y E2E; corridas de regresión con `pytest`; validación del ciclo local de Alembic (`upgrade head` -> `downgrade -1` -> `upgrade head` -> `check`). | Consultas rápidas de 1 comando que el agente principal ya necesita leer en el mismo turno. |
| **`documentador-trazabilidad-contratos`** | [.agents/agents/documentador-trazabilidad-contratos/agent.md](.agents/agents/documentador-trazabilidad-contratos/agent.md) | `flash` | Barridos de exploración de endpoints/DTOs para no saturar el contexto principal; redacción/actualización de contratos para frontend (`GUIA_FRONTEND_*.md`, `trazabilidad/05_*`, `06_*`, `docs/*.md`); creación de avances JSON en `trazabilidad/avances/` (con `decisions` obligatorias), actualización de `01_ESTADO_ACTUAL_PROYECTO.md` y resúmenes de estado. | Preguntas puntuales sobre un único archivo ya abierto en el contexto actual. |

### Protocolo de Coordinación para el Agente Principal / Orchestrator
1. **Flujo Estándar para Nuevas Funcionalidades Complejas (Pipeline por Etapas)**:
   - **Fase 1 (Diseño / Esquema — `pro`)**: Invoca en paralelo o secuencia a `arquitecto-dominio-seguridad` (contratos e invariantes de negocio/RBAC) y/o `especialista-datos-rendimiento` (modelos ORM + migración Alembic + consultas SQL óptimas).
   - **Fase 2 (Implementación — `flash`)**: Delega la codificación de capas (`dtos/`, `repository/`, `services/`, `api/`) a `implementador-api-fastapi` (usa `Workspace: "share"` si varios subagentes editan módulos independientes en paralelo).
   - **Fase 3 (Verificación y Cierre — `flash` en paralelo)**: Invoca en paralelo a `ingeniero-qa-migraciones` (suites AAA + ciclo Alembic) y a `documentador-trazabilidad-contratos` (`GUIA_FRONTEND_*.md` + registro en `trazabilidad/avances/` cuando corresponda).
2. **Tareas Simples o Puntuales**: Para lecturas de 1-2 archivos o correcciones triviales de pocas líneas, resuélvelas directamente en el agente principal sin sobrecosto de delegación.

---

## 3. Reglas Globales Inquebrantables del Proyecto

Todo agente (principal o subagente) está obligado a cumplir las normas detalladas en `.agents/`:

1. **Entorno Local y Protección de Base de Datos** ([.agents/AGENTS.md](.agents/AGENTS.md), [.agents/BUENAS_PRACTICAS_BD.md](.agents/BUENAS_PRACTICAS_BD.md)):
   - Desarrollo y pruebas estrictamente en entorno local (`dev_local`, `python run.py --local`).
   - **Solo lectura directa (`SELECT`)**: Prohibido alterar estructura o datos manualmente en la BD; todo cambio pasa por código y migraciones versionadas de Alembic registradas en `app/models/__init__.py` (prohibido `create_all()` en runtime).
2. **Arquitectura de 4 Capas, DTOs y Presupuesto SQL** ([.agents/BUENAS_PRACTICAS_Y_ESTANDARES_BACKEND.md](.agents/BUENAS_PRACTICAS_Y_ESTANDARES_BACKEND.md)):
   - Separación estricta `Router -> Service -> Repository -> DTO (Pydantic v2)`. Prohibido exponer modelos ORM en respuestas HTTP o llamar repositorios desde routers.
   - Control transaccional (`commit` / `rollback`) exclusivo en `Service`; los repositorios solo usan `flush()`.
   - Presupuesto `X-DB-Round-Trips` en `/api/v1/taller/*` (máx. 1 viaje en `GET`, 2 en mutaciones) y agregaciones en SQL nativo (cero N+1 y cero *Full Table Fetch*).
3. **Excepciones de Dominio, RBAC y Concurrencia**:
   - Usar siempre `app/core/exceptions.py` (`NotFoundException`, `BusinessRuleException`, `ConflictException`, `PermissionException`, `AuthenticationException`); nunca `HTTPException` ni `ValueError` en servicios, ni bloques `except Exception: pass`.
   - Proteger todo endpoint mutante con dependencias de `app/api/deps.py` respetando `enforce_visual_read_only` (rol `VISUAL` bloqueado con 403 en escrituras).
   - Cero I/O bloqueante (`open()`) en funciones `async def` y validación estricta de tamaño/MIME en `app/core/storage/`.
4. **Código Limpio, Observabilidad y Testing** ([.agents/BUENAS_PRACTICAS_CODIGO.md](.agents/BUENAS_PRACTICAS_CODIGO.md)):
   - Funciones con SRP de 5 a 20 líneas, 0 a 2 parámetros ideales (máx. 3 o DTO), CQS, guard clauses Fail-Fast, constantes `Final` y tipado explícito.
   - Uso obligatorio de `logging.getLogger(__name__)`; **prohibido usar `print()`** en el backend.
   - Toda lógica de negocio no trivial requiere tests `pytest` bajo patrón **Arrange-Act-Assert (AAA)** con `AsyncMock`.
5. **Trazabilidad y GitFlow**:
   - Cada avance formal en `trazabilidad/avances/` debe incluir obligatoriamente el bloque `decisions` fundamentado.
   - Ramas `feature/*` hacia `develop` (prohibido merge directo de `feature/*` a `main`) y commits atómicos bajo **Conventional Commits** (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `perf:`), sin mezclar refactorizaciones con nuevas funcionalidades.
