# Plan de Implementación: Idempotencia y Blindaje de Estadías de Taller (Cálculo de Tiempos y Visitas)

## 1. Diagnóstico del Problema y Causa Raíz
- **Síntoma Observado en OT #24:** 
  - La OT fue creada el 24-09-2026 10:16 a.m. (menos de 24 hrs atrás).
  - La UI reporta: "2d 8h en taller" y "Visitas registradas: 3 visitas" (todas rotuladas como `Visita #1` en curso).
- **Causa Raíz Técnica:**
  - En `mantencion_service.py`, el método `_asegurar_ingreso_taller_y_estadia` evalúa:
    ```python
    if hasattr(solicitud, "estadias") and solicitud.estadias is not None:
        estadia_abierta = next((e for e in solicitud.estadias if e.fecha_salida is None), None)
        conteo_prev = len(solicitud.estadias)
    else:
        estadia_abierta, conteo_prev = await self.repo.get_info_estadia_para_ingreso(db, solicitud.id)
    ```
  - Cuando la solicitud se consulta con repositorios que usan `noload(TallerSolicitud.estadias)` (como `get_solicitud_con_detalles`), SQLAlchemy inicializa la colección vacía en memoria `solicitud.estadias = []`.
  - Por ende, `hasattr(...) and solicitud.estadias is not None` es verdadero, `estadia_abierta` queda en `None` y `conteo_prev` es `0`.
  - Cada acción sucesiva (por ejemplo, asignar mecánicos o autoasignar 3 fallas distintas a las 13:14, 13:17 y 14:39) inserta una nueva fila en `taller_solicitud_estadias` con `numero_visita = 1` y `fecha_salida = None`.
  - `calcular_telemetria_estadias` itera sobre todas las estadías y suma el tiempo activo de **cada una** de las 3 estadías en curso, triplicando el tiempo transcurrido (56.3 hrs ≈ 2d 8h).

---

## 2. Objetivos del Plan
1. **Blindaje de Idempotencia en Base de Datos y Servicio:**
   - Evitar bajo cualquier circunstancia que una OT pueda abrir múltiples estadías activas (`fecha_salida IS NULL`).
   - Usar `inspect(solicitud).attrs.estadias.loaded` para saber con total certeza si la relación en memoria está realmente cargada desde la BD o si fue omitida (`noload`/no cargada).
   - Consultar siempre `get_info_estadia_para_ingreso` si la relación no está formalmente cargada.
   - Si ya existe una estadía activa, **no crear una nueva** bajo ninguna circunstancia.
2. **Saneamiento de Datos (Data Fix / Script de Limpieza):**
   - Corregir los registros corruptos en `taller_solicitud_estadias` para la OT #24 (y cualquier otra OT que presente duplicados activos).
   - Fusionar/cerrar las estadías duplicadas espurias conservando la primera fecha de ingreso y ajustando el `numero_visita`.
3. **Validación y Pruebas Unitarias/Integración:**
   - Crear tests automatizados que simulen múltiples llamadas a `_asegurar_ingreso_taller_y_estadia` con y sin `noload` en la relación de estadías.
   - Ejecutar la suite completa de pruebas para garantizar que 100% pasen.
4. **Registro de Trazabilidad:**
   - Documentar el avance en `trazabilidad/avances/0091_YYYYMMDDTHHMMSSZ_fix_idempotencia_estadias_taller.json` y actualizar `01_ESTADO_ACTUAL_PROYECTO.md`.

---

## 3. Plan Paso a Paso de Ejecución

### Fase 1: Corrección en la Lógica de Negocio y Repositorio
- [ ] En `mantencion_service.py` -> `_asegurar_ingreso_taller_y_estadia`:
  - Utilizar `from sqlalchemy import inspect` para verificar `inspect(solicitud).attrs.estadias.loaded`.
  - Solo confiar en `solicitud.estadias` en memoria si la relación fue explícitamente cargada (`is_loaded`). De lo contrario, consultar obligatoriamente `self.repo.get_info_estadia_para_ingreso(db, solicitud.id)`.
  - Si `estadia_abierta` no es `None`, abortar la creación de una nueva estadía y mantener la actual.
  - Asegurar que `numero_visita` se compute correctamente como `max(visitas_existentes) + 1` en lugar de un conteo simple que pueda colisionar si hubo cancelaciones.

### Fase 2: Script de Migración / Saneamiento de Datos
- [ ] Crear un script o migración de datos idempotente para:
  - Detectar OTs con múltiples estadías con `fecha_salida IS NULL`.
  - Para cada OT afectada (ej. OT #24), dejar activa únicamente la primera estadía por `fecha_ingreso` y eliminar o cerrar las duplicadas creadas con minutos de diferencia.
  - Recalcular `solicitud.horas_taller_acumuladas` y sincronizar el estado.

### Fase 3: Pruebas Automatizadas
- [ ] Agregar prueba en `tests/unit/test_mantencion_service.py` o módulo equivalente:
  - Test: `test_asegurar_ingreso_taller_idempotente_no_duplica_estadias_con_noload`:
    - Simula múltiples llamadas sucesivas de toma de fallas/asignaciones sobre una solicitud con relación `estadias` descargada (`noload`).
    - Verifica que se genere exactamente **1 sola estadía** y que las siguientes llamadas sean no-op respecto a la creación de estadías.
  - Ejecutar pytest sobre toda la suite (asegurar los 183+ tests en verde).

### Fase 4: Trazabilidad y Cierre
- [ ] Generar archivo `trazabilidad/avances/0091_20260925T..._fix_idempotencia_estadias_taller.json`.
- [ ] Actualizar `trazabilidad/01_ESTADO_ACTUAL_PROYECTO.md`.
