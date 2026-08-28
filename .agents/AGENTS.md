# Reglas e Instrucciones para Agentes AI (.agents/AGENTS.md)

## 0. Enfoque Exclusivo Backend
- **Repositorio Backend Autónomo:** Este repositorio es exclusivamente de **Backend API** (`BackendTallerNarbus`). El Frontend se maneja en un repositorio completamente separado.
- **Sin Interferencia de Frontend:** Todos los diseños, especificaciones, avances y planes corresponden 100% a endpoints, modelos de datos, servicios, repositorios y reglas de negocio del Backend.

## 1. Entorno de Ejecución y Base de Datos
- **Entorno Local Estricto:** Toda la ejecución, desarrollo y pruebas se realizan de forma **local** (`dev_local`).
- **Restricción de Base de Datos:** Solo se permite el uso de consultas de lectura (**GET / SELECT**) a la base de datos de manera directa para operaciones de verificación. Todas las modificaciones deben realizarse mediante código o migraciones de Alembic.

## 2. DTOs y Manejo Centralizado de Excepciones
- **Uso Obligatorio de DTOs (Pydantic Models):**
  - Todo nuevo endpoint, entrada de datos (`payload`/`request body`) o respuesta (`response_model`) debe contar con su correspondiente **DTO (Data Transfer Object)** definido en la carpeta `dtos/` del módulo respectivo.
  - No se deben exponer directamente los modelos ORM de SQLAlchemy en los controladores.
- **Uso Obligatorio de Excepciones de Dominio:** El proyecto cuenta con un sistema centralizado de excepciones en `app/core/exceptions.py`.
- **Regla en Nuevas Funcionalidades:** Toda nueva mejora, endpoint, servicio o repositorio DEBE utilizar las excepciones de dominio existentes (`NotFoundException`, `BusinessRuleException`, `ConflictException`, `PermissionException`) cuando sea necesario, evitando lanzar `ValueError` o usar bloques `try/except` repetitivos en los routers.

## 3. Trazabilidad del Proyecto (Full Backend)
- **Estructura de la Carpeta `trazabilidad/`:**
  - `trazabilidad/avances/`: Contiene archivos JSON numerados secuencialmente registrando cada avance significativo del backend (ej. `0001_YYYYMMDDTHHMMSSZ_descripcion.json`).
  - `01_ESTADO_ACTUAL_PROYECTO.md`: Documento vivo con el estado general de los módulos y endpoints.
  - `02_CONTENIDO_Y_ALCANZABLE_BACKEND.md`: Especificación técnica del alcance del backend.
  - `03_ESPECIFICACION_MODULOS_NARBUS.md`: Detalle de contratos REST, DTOs y reglas de negocio.
  - `04_PLAN_IMPLEMENTACION_BACKEND.md`: Plan global de desarrollo del Backend.
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

## 4. Logging en el Backend
- **Uso de Logger:** Se debe implementar logging utilizando el módulo estándar de Python (`logging.getLogger(__name__)`) siempre que sea necesario en servicios, repositorios, middleware y exception handlers.
- **Trazabilidad de Eventos:** Registrar información relevante (eventos críticos, fallos, cambios de estado o excepciones no controladas) para asegurar observabilidad en el backend.

## 5. Metodología GitFlow
- **Flujo de Ramas:** El desarrollo se realiza en ramas `feature/*` que se integran a `develop` mediante la estrategia de GitFlow.
- **Prohibido Merge Directo a Main:** NUNCA se realiza merge directo de ramas de características (`feature/*`) hacia la rama `main`.
