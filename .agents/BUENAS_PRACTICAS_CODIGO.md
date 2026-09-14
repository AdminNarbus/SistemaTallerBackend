# Guía de Buenas Prácticas de Programación, Código Limpio y Estándares de Software (.agents)

Este documento establece las directrices de ingeniería de software, código limpio (*Clean Code*), principios SOLID, diseño de funciones, nomenclatura y estándares de calidad para el repositorio **`BackendTallerNarbus`**. Complementa las guías específicas de base de datos ([.agents/BUENAS_PRACTICAS_BD.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_BD.md)) y arquitectura backend ([.agents/BUENAS_PRACTICAS_Y_ESTANDARES_BACKEND.md](file:///c:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/.agents/BUENAS_PRACTICAS_Y_ESTANDARES_BACKEND.md)).

---

## 1. Principio de Responsabilidad Única (SRP)

> "Una función, método, clase o módulo debe tener una, y solo una, razón para cambiar."  
> — Robert C. Martin (Uncle Bob)

### 1.1 SRP Aplicado a Funciones y Métodos
En el desarrollo de servicios y utilitarios de `BackendTallerNarbus`, cada función o método debe:
1. **Hacer una sola cosa y hacerla de forma excelente.**
2. **Operar en un único nivel de abstracción (SLAP - Single Level of Abstraction Principle):** No mezclar lógica de negocio de alto nivel con detalles de bajo nivel como formateo de cadenas, manipulación de fechas o queries SQL directas.
3. **Adoptar el patrón Coordinador vs. Especialista:** Las funciones de entrada a casos de uso coordinan los pasos secuenciales delegando la ejecución a funciones o métodos especializados.
4. **Nombres descriptivos sin conectores:** Evitar conjunciones como "y" u "o" (`guardar_y_notificar`, `validar_y_crear`). Si una función requiere "y", usualmente tiene más de una responsabilidad.

### ❌ Anti-Patrón: Violación de SRP en Servicio
```python
# ❌ INCORRECTO: Múltiples razones para cambiar (validación, cálculo, persistencia y correo)
async def registrar_salida_taller(solicitud_id: int, kilometraje: int, usuario_id: int, db: AsyncSession):
    # 1. Validación de reglas
    solicitud = await db.get(SolicitudTaller, solicitud_id)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if solicitud.estado != EstadoSolicitud.EN_PROCESO:
        raise HTTPException(status_code=400, detail="Estado incompatible")
        
    # 2. Lógica y cálculo
    if kilometraje < solicitud.bus.kilometraje_actual:
        raise HTTPException(status_code=400, detail="Kilometraje menor al registrado")
    diferencia_km = kilometraje - solicitud.bus.kilometraje_actual
    
    # 3. Mutación de base de datos
    solicitud.estado = EstadoSolicitud.FINALIZADA
    solicitud.bus.kilometraje_actual = kilometraje
    solicitud.fecha_salida = datetime.utcnow()
    await db.commit()
    
    # 4. Notificación externa
    mensaje = f"Bus {solicitud.bus.patente} ha salido del taller con {kilometraje} km."
    await smtp_client.send_email("jefe_operaciones@narbus.cl", "Salida de Bus", mensaje)
    return {"status": "ok", "diferencia_km": diferencia_km}
```

### ✅ Patrón Recomendado: SRP y Función Coordinadora
```python
# ✅ CORRECTO: Funciones con responsabilidad única y orquestador limpio
def _validar_transicion_salida(solicitud: Optional[SolicitudTaller], nuevo_kilometraje: int) -> None:
    if not solicitud:
        raise NotFoundException("Solicitud de taller no encontrada")
    if solicitud.estado != EstadoSolicitud.EN_PROCESO:
        raise BusinessRuleException(f"No se puede finalizar una solicitud en estado {solicitud.estado.value}")
    if nuevo_kilometraje < solicitud.bus.kilometraje_actual:
        raise BusinessRuleException("El kilometraje de salida no puede ser menor al actual")

def _aplicar_datos_salida(solicitud: SolicitudTaller, nuevo_kilometraje: int, fecha_salida: datetime) -> int:
    diferencia_km = nuevo_kilometraje - solicitud.bus.kilometraje_actual
    solicitud.estado = EstadoSolicitud.FINALIZADA
    solicitud.fecha_salida = fecha_salida
    solicitud.bus.kilometraje_actual = nuevo_kilometraje
    return diferencia_km

class TallerService:
    def __init__(self, taller_repo: TallerRepository, notification_service: NotificationService):
        self.repo = taller_repo
        self.notifications = notification_service

    async def registrar_salida_taller(
        self,
        db: AsyncSession,
        solicitud_id: int,
        nuevo_kilometraje: int
    ) -> SalidaTallerResponseDTO:
        solicitud = await self.repo.obtener_solicitud_con_bus(db, solicitud_id)
        _validar_transicion_salida(solicitud, nuevo_kilometraje)
        
        ahora = datetime.now(timezone.utc)
        diferencia_km = _aplicar_datos_salida(solicitud, nuevo_kilometraje, ahora)
        
        await db.commit()
        await self.notifications.notificar_salida_bus(solicitud.bus.patente, nuevo_kilometraje)
        
        return SalidaTallerResponseDTO(
            solicitud_id=solicitud.id,
            patente=solicitud.bus.patente,
            kilometraje_salida=nuevo_kilometraje,
            diferencia_km=diferencia_km
        )
```

### 1.2 Señales de Violación del SRP (Code Smells)
- Dificultad para resumir la función en una sola frase descriptiva.
- Funciones con más de 20-30 líneas de código o más de 2 niveles de indentación (`if` o bucles anidados).
- Mezcla de contratos HTTP, sentencias SQL y reglas de negocio en el mismo bloque.
- Cambios frecuentes en el mismo archivo por motivos de negocio totalmente dispares.

---

## 2. Principios SOLID Aplicados a FastAPI y SQLAlchemy

| Principio | Significado | Aplicación en BackendTallerNarbus |
|---|---|---|
| **S** – Single Responsibility | Una sola responsabilidad por módulo/clase. | Routers reciben HTTP, Services resuelven lógica de negocio, Repositorios gestionan SQL, DTOs validan payloads. |
| **O** – Open/Closed | Abierto a extensión, cerrado a modificación. | Uso de interfaces y proveedores configurables (ej. `StorageProvider` para Google Cloud Storage o Almacenamiento Local) sin alterar la lógica de quien consume el archivo. |
| **L** – Liskov Substitution | Subtipos sustituibles sin alterar comportamiento. | Si un servicio depende de un `BaseRepository` o `BaseStorageClient`, cualquier implementación derivada debe funcionar sin romper contratos esperados. |
| **I** – Interface Segregation | Interfaces pequeñas y específicas. | Repositorios y servicios enfocados por dominio (`MecanicosRepository`, `PautasRepository`) en lugar de un monolítico `MegaTallerRepository`. |
| **D** – Dependency Inversion | Depender de abstracciones, no de detalles concretos. | Inyección de dependencias mediante `Depends()` de FastAPI para sesiones de BD (`AsyncSession`), clientes y servicios. |

---

## 3. Funciones y Métodos Limpios

### ✅ OBLIGATORIO (DOs)
1. **Longitud concisa (5 a 20 líneas):** Las funciones deben ser compactas y caber en una pantalla sin scroll vertical. Si una función supera las 25-30 líneas, es imperativo analizar la extracción de subfunciones puras o utilitarias.
2. **Pocos parámetros (0 a 2 ideal, 3 máximo):** Si una función requiere 4 o más parámetros, es una señal inequívoca de que los datos deben encapsularse en un DTO Pydantic, un esquema o un Value Object.
3. **Cero efectos secundarios ocultos (*Side Effects*):** Una función con nombre `calcular_desgaste_neumatico()` solo debe realizar el cálculo matemático. Bajo ninguna circunstancia debe modificar la base de datos o mutar variables globales silenciosamente.
4. **Command-Query Separation (CQS):** Un método debe o bien ejecutar una mutación/comando (crear, actualizar, eliminar) o bien retornar información (consulta/query), evitando mezclar ambas responsabilidades salvo retornos explícitos del recurso creado.
5. **Funciones puras para cálculos y validaciones complejas:** Aislar reglas matemáticas (desgastes de neumáticos, cálculo de horas de turno, porcentajes de avance de pautas) en funciones puras sin dependencias de I/O ni bases de datos, permitiendo testing unitario instantáneo.

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA usar flags booleanos como parámetros de control de flujo:**  
   *Por qué:* `guardar_solicitud(solicitud, notificar=True)` oscurece la lectura del código y revela que la función hace dos cosas distintas. En su lugar, declarar dos métodos claros o componer en el servicio (`guardar_solicitud` y luego `notificar_solicitud`).
2. **NUNCA alterar argumentos mutables pasados por referencia sin declararlo explícitamente:**  
   *Por qué:* Modificar listas o diccionarios recibidos como argumentos genera efectos colaterales impredecibles en capas superiores.

---

## 4. Convenciones de Nomenclatura y Claridad Semántica

### ✅ OBLIGATORIO (DOs)
1. **Nombres que revelen intención de negocio:**
   - Preferir `dias_hasta_proxima_mantencion` sobre `dias`, `d` o `delta`.
   - Preferir `solicitudes_pendientes_asignacion` sobre `lista1` o `datos`.
2. **Verbos de acción claros y precisos para funciones:**
   - Consultas: `obtener_bus_por_patente`, `listar_mecanicos_activos`, `buscar_solicitudes_abiertas`.
   - Mutaciones: `crear_orden_trabajo`, `cerrar_avance_turno`, `anular_solicitud`.
   - Verificaciones: `validar_stock_repuesto`, `verificar_disponibilidad_mecanico`.
3. **Prefijos semánticos para variables y métodos booleanos:**
   - Usar `es_`, `esta_`, `tiene_`, `puede_` (ej. `es_critico`, `esta_aprobada`, `tiene_pauta_completa`, `puede_iniciar_turno`).
4. **Constantes con nombre en lugar de "Números Mágicos" (*Magic Numbers*):**
   - Declarar constantes en mayúsculas (`SNAKE_CASE`) a nivel de módulo o configuración:
   ```python
   # ✅ CORRECTO
   PRESION_MINIMA_PSI: Final[float] = 100.0
   UMBRAL_PROFUNDIDAD_CRITICA_MM: Final[float] = 3.0
   MAX_INTENTOS_REINTENTO_STORAGE: Final[int] = 3
   ```
5. **Consistencia en el vocabulario del repositorio:** Si se opta por `obtener_` para recuperar una entidad y `listar_` para colecciones, mantener este estándar en todos los servicios y repositorios sin alternar arbitrariamente con `get_`, `fetch_` o `retrieve_`.

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA usar abreviaturas crípticas o nombres de una sola letra:**  
   *Por qué:* `sol` (¿solicitud o solución?), `m` (¿mecánico, mes, minuto?), `calc` (¿calculadora o calcular?). El código se lee 10 veces más de lo que se escribe.
2. **NUNCA incrustar números mágicos o cadenas de texto sueltas en la lógica:**  
   *Por qué:* Si el número `0.19` o el límite `80` cambian, rastrear cadenas sin nombre en decenas de archivos es propenso a errores graves.

---

## 5. Principios Pragmáticos: DRY, KISS y YAGNI

### 5.1 DRY (Don't Repeat Yourself)
- **Eliminar duplicación de lógica de negocio:** Si la regla de validación de RUT o el cálculo de desgaste de neumáticos se repite en dos o más lugares, extraerlo a un módulo compartido (`app/core/utils/` o métodos de modelo).
- **Cuidado con la trampa de la abstracción prematura:** No unificar dos bloques de código que son idénticos por coincidencia pero que pertenecen a dominios distintos y evolucionarán de manera diferente. La duplicación accidental es menos costosa que una abstracción equivocada.

### 5.2 KISS (Keep It Simple, Stupid)
- Priorizar la implementación más simple y legible que resuelva el problema de negocio.
- Evitar metaprogramación innecesaria, decoradores crípticos o patrones de diseño complejos cuando una función directa o una clase estándar es suficiente.

### 5.3 YAGNI (You Aren't Gonna Need It)
- Implementar estrictamente los requerimientos actuales del backend.
- No construir frameworks internos, parámetros hipotéticos ni tablas suplementarias "por si en el futuro se necesita". Cuando el requerimiento real surja, se diseñará con la información precisa.

---

## 6. Manejo Robusto de Errores y "Fail Fast"

### ✅ OBLIGATORIO (DOs)
1. **Patrón "Fail Fast" (Falla Rápido) con Cláusulas de Guarda (*Guard Clauses*):**  
   Validar precondiciones, nulabilidad y estados al inicio de la función. Retornar o lanzar la excepción de inmediato, reduciendo los niveles de indentación:
   ```python
   # ✅ CORRECTO: Guard clauses limpias
   def verificar_inicio_tarea(mecanico: Usuario, solicitud: SolicitudTaller) -> None:
       if not mecanico.is_active:
           raise BusinessRuleException("El mecánico se encuentra inactivo")
       if not mecanico.rol == RolUsuario.MECANICO:
           raise PermissionException("El usuario asignado no posee rol de mecánico")
       if solicitud.estado != EstadoSolicitud.ASIGNADA:
           raise BusinessRuleException(f"No se puede iniciar tarea en estado {solicitud.estado.value}")
   ```
2. **Utilizar Excepciones de Dominio Específicas:**  
   Utilizar las excepciones jerárquicas de `app/core/exceptions.py` (`NotFoundException`, `BusinessRuleException`, `ConflictException`, etc.) en lugar de retornar valores centinela (`None`, `-1`, cadenas vacías).
3. **Separar el flujo de error de la lógica feliz:**  
   Mantener el cuerpo del servicio enfocado en el flujo principal del caso de uso. Los manejadores globales de excepciones de FastAPI capturan las excepciones de dominio y construyen la respuesta JSON adecuada.

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA retornar `None` o tuplas de error silenciosas para ocultar fallos:**  
   *Por qué:* Obliga a los llamadores a realizar comprobaciones defensivas constantes `if resultado is None:` y propaga estados inválidos silenciosamente.
2. **NUNCA capturar excepciones genéricas para ignorarlas:**  
   *Por qué:* `except Exception: pass` destruye la trazabilidad y convierte errores críticos en anomalías invisibles.
3. **NUNCA anidar bloques `try/except` masivos dentro del flujo de negocio:**  
   *Por qué:* Dificulta la lectura del código y mezcla la infraestructura con las reglas operacionales.

---

## 7. Comentarios, Tipado Estricto y Documentación

### ✅ OBLIGATORIO (DOs)
1. **Código autodocumentado:** El código debe ser claro por sí mismo gracias a nombres precisos y funciones pequeñas.
2. **Comentar el "Por Qué", nunca el "Qué":**  
   Los comentarios deben justificar decisiones no evidentes, restricciones de negocio complejas, limitaciones del motor SQL o referencias a normativas de transporte.
   ```python
   # ✅ CORRECTO: Explica la justificación de negocio o arquitectura
   # Se utiliza un umbral de 3.0 mm según la normativa técnica del Ministerio de Transportes para buses interurbanos.
   if profundidad_minima < UMBRAL_NORMATIVA_TRANSPORTE_MM:
       marcar_neumatico_para_reemplazo(neumatico)
   ```
3. **Docstrings en interfaces públicas y servicios:**  
   Documentar contratos públicos, parámetros y excepciones lanzadas en servicios principales mediante formato estándar.
4. **Tipado estricto (Type Annotations) con Python 3.11+:**  
   Todas las funciones y métodos deben declarar explícitamente los tipos de sus argumentos y valor de retorno (`-> None`, `-> SolicitudDTO`, etc.).

### ❌ PROHIBIDO (DON'Ts)
1. **NUNCA dejar bloques de código comentado (*Dead Code*):**  
   *Por qué:* El control de versiones (Git) existe precisamente para consultar el historial. El código comentado confunde a los desarrolladores y ensucia el repositorio.
2. **NUNCA mantener historiales de cambios manuales ni listas de autores en la cabecera del archivo:**  
   *Por qué:* Git registra automáticamente quién, cuándo y por qué modificó cada línea.
3. **NUNCA escribir comentarios redundantes que solo repiten el código:**  
   *Por qué:* `# Incrementa el contador en 1 -> contador += 1` no aporta valor y genera ruido visual.

---

## 8. Estructura Modular, Cohesión y Linters

### ✅ OBLIGATORIO (DOs)
1. **Un archivo, un propósito bien delimitado:** Cada módulo en `app/` debe agrupar componentes estrechamente cohesionados.
2. **Alta cohesión y bajo acoplamiento:** Los servicios deben interactuar entre sí a través de contratos claros y DTOs, evitando dependencias circulares entre módulos.
3. **Formateo y análisis estático automatizado:**  
   Seguir las convenciones de PEP 8 y aplicar formateadores estándar (Black, Flake8 o Ruff) para mantener uniformidad estilística absoluta en todo el repositorio.
4. **Orden canónico de imports en archivos Python:**
   - 1º Grupo: Librería estándar de Python (`typing`, `datetime`, `asyncio`, `uuid`).
   - 2º Grupo: Dependencias de terceros (`fastapi`, `sqlalchemy`, `pydantic`).
   - 3º Grupo: Módulos internos del proyecto (`app.core.*`, `app.modules.*`).

---

## 9. Estrategia de Testing y Aislamiento

### ✅ OBLIGATORIO (DOs)
1. **Patrón AAA (Arrange, Act, Assert):**  
   Estructurar cada prueba unitaria en tres fases visuales claramente separadas:
   ```python
   # ✅ CORRECTO: Estructura AAA
   def test_calcular_desgaste_neumatico_retorna_alerta_si_supera_umbral():
       # Arrange (Preparar datos)
       profundidad_inicial = 12.0
       profundidad_actual = 2.5
       
       # Act (Ejecutar función)
       resultado = calcular_estado_desgaste(profundidad_inicial, profundidad_actual)
       
       # Assert (Verificar resultado)
       assert resultado.es_critico is True
       assert resultado.milimetros_restantes == 2.5
   ```
2. **Aislamiento mediante Mocks:**  
   En las pruebas de la capa de Servicio, aislar la persistencia utilizando mocks de los repositorios (`AsyncMock`), permitiendo evaluar la lógica de negocio sin depender de una base de datos real.
3. **Cobertura exhaustiva de casos borde (*Edge Cases*):**  
   Probar valores límites, colecciones vacías, valores nulos, transiciones de estado imposibles y divisiones por cero.

---

## 10. Control de Versiones y Convención de Commits

### ✅ OBLIGATORIO (DOs)
1. **Commits atómicos y pequeños:** Cada commit debe representar un cambio lógico unitario y coherente que compile y funcione por sí mismo.
2. **Estándar Conventional Commits:** Utilizar mensajes estructurados que permitan trazabilidad automática:
   - `feat:` Nueva funcionalidad o endpoint en el backend.
   - `fix:` Corrección de un bug o comportamiento anómalo.
   - `refactor:` Refactorización de código sin alterar su comportamiento externo ni agregar endpoints.
   - `perf:` Optimización de rendimiento o consultas SQL.
   - `test:` Adición o corrección de pruebas automatizadas.
   - `docs:` Modificaciones exclusivamente a documentación o guías en `.agents/`.
   - `chore:` Tareas de mantenimiento, dependencias o configuración sin impacto en producción.
3. **Separación estricta de refactorizaciones y nuevas características:** NUNCA mezclar una refactorización de arquitectura con una nueva funcionalidad de negocio en el mismo commit.

---

## 11. Checklist Rápido de Calidad Previa a la Entrega

Antes de dar por completada una tarea, servicio o Pull Request en `BackendTallerNarbus`, verificar:

- [ ] **SRP:** ¿Cada función y clase hace una sola cosa y tiene un solo motivo para cambiar?
- [ ] **SLAP:** ¿Las funciones coordinadoras operan en un único nivel de abstracción sin mezclar detalles de bajo nivel?
- [ ] **Tamaño:** ¿Las funciones tienen entre 5 y 20 líneas (máximo 30)?
- [ ] **Parámetros:** ¿Tienen 3 o menos argumentos (o están agrupados en un DTO)?
- [ ] **Flags:** ¿Se eliminaron los parámetros booleanos de control de flujo?
- [ ] **CQS:** ¿Se respeta la separación entre comandos que mutan y consultas que leen?
- [ ] **Nomenclatura:** ¿Los nombres revelan intención de negocio sin abreviaturas oscuras ni números mágicos?
- [ ] **Fail Fast:** ¿Se validan las precondiciones al inicio mediante guard clauses?
- [ ] **Excepciones:** ¿Se utilizan excepciones de dominio de `app/core/exceptions.py` sin bloques `except Exception: pass`?
- [ ] **Comentarios:** ¿Se eliminó todo el código comentado y los comentarios redundantes?
- [ ] **Tipado:** ¿Todas las firmas cuentan con anotaciones de tipo explícitas?
- [ ] **Testing:** ¿Se añadieron tests con estructura AAA cubriendo el camino feliz y los casos borde?
- [ ] **Git:** ¿El mensaje de commit sigue Conventional Commits y representa un cambio atómico?
