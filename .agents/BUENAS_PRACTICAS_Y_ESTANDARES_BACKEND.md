# Guía de Buenas Prácticas, Obligaciones y Prohibiciones de Backend (.agents)

Este documento establece las directrices de ingeniería de software, arquitectura limpia, seguridad, rendimiento y buenas prácticas para el desarrollo y mantenimiento del repositorio **`BackendTallerNarbus`**.

---

## 1. Arquitectura Limpia y Separación de Responsabilidades

### ✅ OBLIGATORIO (DOs)
1. **Separar estrictamente en 4 capas:**
   - **Router / API:** Recibe peticiones HTTP, valida DTOs mediante Pydantic y delega inmediatamente al Servicio. *Por qué:* Mantiene los controladores delgados, desacoplados del framework y fáciles de testear.
   - **Service (Caso de Uso):** Contiene **toda** la lógica de negocio, reglas operacionales, validaciones de estado, orquestación entre múltiples repositorios y coordinación de transacciones. *Por qué:* Centraliza la inteligencia del negocio en un único lugar testeable sin requerir peticiones HTTP.
   - **Repository (Persistencia):** Solo ejecuta consultas SQL y operaciones CRUD (`select`, `add`, `flush`, `delete`) con SQLAlchemy. *Por qué:* Aísla los detalles de la base de datos y permite cambiar o mockear el almacenamiento sin alterar la lógica de negocio.
   - **DTOs (Data Transfer Objects):** Todos los contratos de entrada y salida deben ser modelos de Pydantic. *Por qué:* Garantiza validación de tipos estricta y evita fugas de información interna.
2. **Inyección de Dependencias:** Usar las dependencias de FastAPI (`Depends`) para entregar la sesión de base de datos (`AsyncSession`) y el usuario autenticado. *Por qué:* Facilita el intercambio de implementaciones y el aislamiento en tests unitarios e integrales.

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA colocar lógica de negocio en los Repositorios (Anti-patrón "Smart Repository").**  
   *Por qué:* Los repositorios no deben conocer reglas como "si faltan ítems de la pauta se debe rechazar" o calcular duraciones de turno. Esto impide reusar consultas y rompe el Principio de Responsabilidad Única (SRP).
2. **NUNCA llamar a Repositorios directamente desde los Routers saltándose la capa de Servicio.**  
   *Por qué:* Genera duplicación de lógica en múltiples endpoints y conduce a servicios anémicos o inexistentes.
3. **NUNCA exponer modelos ORM de SQLAlchemy directamente en las respuestas HTTP de los Routers.**  
   *Por qué:* Provoca acoplamiento del contrato de la API con el esquema físico de la base de datos, expone campos sensibles (como contraseñas o hashes) y genera errores de serialización con relaciones cargadas perezosamente (*Lazy Loading*).

---

## 2. Transacciones y Persistencia en la Arquitectura (Service vs. Repository)

> Para las directrices canónicas de diseño relacional, modelado con SQLAlchemy 2.0 y gestión de migraciones con Alembic, consultar obligatoriamente [.agents/BUENAS_PRACTICAS_BD.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_BD.md).

### ✅ OBLIGATORIO (DOs)
1. **Control Transaccional en la Capa de Servicio (Unit of Work):** La capa de servicio orquesta los casos de uso y debe decidir cuándo persistir de forma atómica (`await db.commit()`) o revertir (`await db.rollback()`), mientras que los repositorios deben utilizar `await db.flush()` para sincronizar IDs generados sin cerrar la transacción.  
   *Por qué:* Si una operación consta de múltiples pasos y uno falla, se debe revertir de forma íntegra para no dejar la base de datos en estado inconsistente.
2. **Paginación obligatoria en endpoints de listado:** Toda consulta que devuelva colecciones debe soportar parámetros `skip` y `limit` (o `page` y `page_size`) con límites superiores razonables (ej. máximo 100 registros).  
   *Por qué:* Previene denegaciones de servicio y saturación de memoria por consultas desmedidas a tablas grandes.
3. **Adhesión estricta a los Estándares de Base de Datos:** Todo cambio estructural de tablas, columnas o índices debe implementarse exclusivamente mediante migraciones versionadas de Alembic según [.agents/BUENAS_PRACTICAS_BD.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_BD.md).

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA ejecutar `await db.commit()` dentro de los métodos individuales de un Repositorio.**  
   *Por qué:* Rompe la atomicidad de transacciones compuestas coordinadas por el servicio. Si el repositorio A hace commit y el repositorio B falla a continuación, la operación del repositorio A ya no se puede revertir.
2. **NUNCA ejecutar sentencias DDL ni `create_all()` en tiempo de ejecución de la aplicación.**  
   *Por qué:* Bloquea la base de datos en entornos concurrentes y destruye la reproducibilidad del esquema (ver reglas en [.agents/BUENAS_PRACTICAS_BD.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_BD.md)).

---

## 3. Rendimiento y Optimización de Consultas SQL

### ✅ OBLIGATORIO (DOs)
1. **Cálculos y métricas agregadas en SQL:** Todo conteo, suma, promedio o agrupación para tableros y analítica debe resolverse con funciones nativas del motor relacional (`func.count()`, `func.sum()`, `GROUP BY`, `HAVING`).  
   *Por qué:* Los motores relacionales (PostgreSQL) están optimizados en C para procesar millones de filas en milisegundos mediante índices.
2. **Filtrar en la base de datos con cláusulas `WHERE` e índices adecuados:**  
   *Por qué:* Descargar miles de registros a la memoria RAM de Python para luego filtrarlos con `if bus.startswith(...)` desperdicia ancho de banda de red, CPU y memoria.
3. **Cargar relaciones explícitamente solo cuando sean necesarias:** Usar `selectinload()` o `joinedload()` de forma deliberada en las consultas del repositorio según el caso de uso específico.  
   *Por qué:* Evita el clásico problema de N+1 consultas sin sobrecargar la memoria con datos que no se van a utilizar.

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA hacer "Full Table Fetch" para calcular estadísticas en memoria de Python.**  
   *Por qué:* Descargar toda la base de datos y recorrerla con bucles `for` genera riesgos críticos de **Out Of Memory (OOM)** y bloquea los recursos del servidor a medida que la empresa crece.
2. **NUNCA ejecutar consultas dentro de un bucle `for` (Problema N+1).**  
   *Por qué:* Si se procesan 50 elementos, se ejecutan 50 consultas individuales en lugar de 1 sola consulta con la cláusula `IN (:valores)`.
3. **NUNCA usar `lazy="selectin"` de forma indiscriminada en las relaciones de los modelos ORM.**  
   *Por qué:* Provoca "tormentas de SELECTs" (*Select Storm*), disparando múltiples consultas SQL secundarias cada vez que se carga una entidad, incluso para consultas simples donde no se requerían dichas relaciones.

---

## 4. Concurrencia Asíncrona y Manejo de Archivos (I/O)

### ✅ OBLIGATORIO (DOs)
1. **Usar operaciones de disco asíncronas o pool de hilos:** Guardar archivos en disco utilizando `aiofiles` o encapsulando el I/O síncrono mediante `await asyncio.to_thread(funcion_escritura)`.  
   *Por qué:* FastAPI opera sobre un Event Loop asíncrono de hilo único por worker. Toda operación síncrona bloqueante (`with open()`) detiene por completo la atención de otras peticiones entrantes.
2. **Validación estricta de archivos subidos:**
   - Validar tamaño máximo permitido (ej. máximo 5 MB o 10 MB).
   - Validar tipo de contenido mediante encabezados mágicos (MIME type real: `image/jpeg`, `image/png`, `image/webp`).
   - Sanitizar nombres de archivo y generar nombres únicos con `uuid4()`.  
   *Por qué:* Previene saturación de disco (DoS), ataques de path traversal y ejecución de binarios maliciosos.

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA usar `open()` de la librería estándar de Python directamente en funciones `async def`.**  
   *Por qué:* Congela el Event Loop de AsyncIO mientras dura la transferencia de bytes hacia el disco.
2. **NUNCA confiar ciegamente en `UploadFile.filename` o `UploadFile.content_type` provisto por el cliente.**  
   *Por qué:* Estos valores provienen del navegador del usuario y pueden ser manipulados maliciosamente por atacantes.

---

## 5. Manejo de Errores y Excepciones de Dominio

### ✅ OBLIGATORIO (DOs)
1. **Usar Excepciones de Dominio centralizadas (`app/core/exceptions.py`):**
   - `NotFoundException` para recursos inexistentes (HTTP 404).
   - `BusinessRuleException` para transiciones de estado inválidas o reglas violadas (HTTP 422).
   - `ConflictException` para colisiones de datos únicos o duplicados (HTTP 409).
   - `PermissionException` para accesos no autorizados por rol (HTTP 403).
   - `AuthenticationException` para sesiones inválidas o expiradas (HTTP 401).  
   *Por qué:* Desacopla la lógica interna del protocolo HTTP y permite que los manejadores globales den un formato uniforme de error a toda la API.
2. **Propagar o registrar excepciones con traceback completo:** En caso de capturar excepciones en capas inferiores, registrarlas con `logger.error(..., exc_info=True)` antes de lanzar una excepción de dominio.  
   *Por qué:* Facilita la observabilidad y depuración de errores en producción.

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA tragar excepciones con bloques silenciosos (`except Exception: pass` o `except: pass`).**  
   *Por qué:* Oculta bugs graves en silencio y hace imposible diagnosticar fallos en producción.
2. **NUNCA lanzar `HTTPException` directamente desde capas de servicio o repositorios.**  
   *Por qué:* Acopla la lógica de negocio al framework web FastAPI/Starlette y rompe la arquitectura limpia.
3. **NUNCA exponer mensajes internos de excepción (`str(e)`) al cliente en respuestas HTTP (especialmente errores de base de datos o contraseñas).**  
   *Por qué:* Fuga de información sensible (nombres de tablas, credenciales, configuración de red) que facilita vectores de ataque.

---

## 6. Diseño y Buenas Prácticas en REST APIs

### ✅ OBLIGATORIO (DOs)
1. **Sustantivos en plural y minúsculas para recursos:** Usar rutas como `/api/v1/buses`, `/api/v1/mantencion/solicitudes`, `/api/v1/neumaticos/reportes`.  
   *Por qué:* Sigue el estándar de diseño RESTful internacional, facilitando la integración con cualquier cliente web o móvil.
2. **Verbos HTTP semánticos:**
   - `GET` para lectura (idempotente y seguro).
   - `POST` para creación o acciones operacionales específicas.
   - `PUT` para reemplazo completo.
   - `PATCH` para actualización parcial de campos.
   - `DELETE` para eliminación o baja lógica.
3. **Declarar siempre el `response_model` en cada endpoint:**  
   *Por qué:* Permite a FastAPI documentar el contrato automáticamente en OpenAPI/Swagger y garantiza que solo se serialicen los campos autorizados.

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA usar camelCase ni verbos en las URLs de endpoints (ej. `/formularioNeumatico` o `/crearBus`).**  
   *Por qué:* Vulnera los estándares REST y dificulta la consistencia de la arquitectura.
2. **NUNCA dejar endpoints que alteren datos sin protección de autenticación.**  
   *Por qué:* Permite inyecciones anónimas no autorizadas de datos.
3. **NUNCA devolver HTTP 200 en endpoints de verificación de salud (`health`) si la base de datos está caída.**  
   *Por qué:* Los balanceadores de carga asumirán que el servicio está operativo cuando en realidad no puede procesar solicitudes.

---

## 7. Logging y Observabilidad

### ✅ OBLIGATORIO (DOs)
1. **Usar el logger estándar de Python en todos los módulos:**
   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```
   *Por qué:* Permite jerarquía por paquetes, control de nivel dinámico por entorno y salida a archivos rotativos estructurados.
2. **Elegir el nivel semántico adecuado:**
   - `DEBUG`: Detalles minuciosos de queries o parámetros (solo dev).
   - `INFO`: Hitos significativos del negocio (solicitud creada, bus liberado, login exitoso).
   - `WARNING`: Situaciones anómalas controladas (usuario inactivo intentando acceder, recurso no encontrado).
   - `ERROR` / `CRITICAL`: Fallos del sistema, caídas de BD o errores no previstos.

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA usar `print()` en ninguna parte del código backend.**  
   *Por qué:* No incluye timestamps, no tiene niveles de filtrado, no va al archivo de log rotativo y perjudica el rendimiento.

---

## 8. Calidad de Código, Limpieza y Mantenimiento

> Las directrices detalladas de código limpio, funciones compactas, principios SOLID, nomenclatura semántica, "Fail Fast", testing unitario y Conventional Commits se encuentran documentadas de forma canónica en [.agents/BUENAS_PRACTICAS_CODIGO.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_CODIGO.md).

### ✅ OBLIGATORIO (DOs)
1. **Adherirse a los Principios SOLID y Código Limpio:** Todo nuevo desarrollo o refactorización debe cumplir estrictamente con las reglas de [.agents/BUENAS_PRACTICAS_CODIGO.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_CODIGO.md) (funciones de 5-20 líneas, 0-2 parámetros, CQS, sin flags booleanos, constantes nombradas y guard clauses).
2. **Eliminar código muerto o prototipos no utilizados:** Archivos de prueba obsoletos, servicios sustituidos o DTOs en desuso deben eliminarse inmediatamente del repositorio.  
   *Por qué:* Reduce la carga cognitiva de los desarrolladores y evita que otros agentes o programadores reutilicen código defectuoso por error.
3. **Configurar correctamente las herramientas de testing en `pytest.ini` (`pythonpath = .`):**  
   *Por qué:* Asegura que los tests unitarios y de integración se ejecuten sin errores de importación desde cualquier terminal o tubería de CI/CD.

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA dejar archivos de código huérfanos ni código comentado bajo la excusa de "por si acaso".**  
   *Por qué:* Para recuperar código histórico existe el control de versiones con Git. Mantener código comentado degrada la legibilidad y confunde a los desarrolladores y agentes AI.
