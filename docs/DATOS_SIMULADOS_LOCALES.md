# Carga local de la simulación Dashboard

La revisión `032_dashboard_simulados_local` carga exclusivamente las tablas de
`C:\Users\Usuario\Desktop\chatgptWork\Dashboard\data\simulados\dashboard_data.json`
y `talleres_extension.json`, según el snapshot del 27-10-2026. No carga las 41 OT
observacionales del JSON real. Los maestros de ese JSON se usan únicamente para
resolver las referencias de buses, roles y siete mecánicos.

El snapshot comprimido está en `alembic/data/dashboard_simulados_20261027.json.gz`.
Incluye metadatos con SHA-256 de los tres archivos fuente; no incluye contraseñas
ni hashes de contraseñas originales. Las fuentes originales no se modifican.

## Aplicar

Requiere `ENVIRONMENT=dev_local`, PostgreSQL en loopback y una base sin OT.
Los buses deben existir por número y las ciudades por código. La carga aborta
si faltan referencias o los buses ya tienen marcas de permanencia en taller.

```powershell
.\.venv\Scripts\python.exe -m alembic -x dashboard_simulados=1 upgrade head
```

Un `upgrade head` ordinario registra la revisión pero **omite los datos**.
No se ejecuta esta carga por defecto durante el inicio de la API. Si la revisión
ya fue aplicada sin la opción, volver a 031 y aplicar 032 con la opción.
Una segunda ejecución de upgrade no duplica filas.

## Contenido y adaptaciones

| Tabla | Filas cargadas |
|---|---:|
| usuarios de referencia sin acceso | 8 |
| talleres | 5 |
| taller_solicitudes | 409 |
| taller_solicitud_detalles | 1253 |
| taller_solicitud_estadias | 397 |
| taller_solicitud_mecanicos | 1445 |
| taller_asignacion_fallas | 1451 |
| taller_falla_eventos | 2330 |
| taller_resultado_operaciones | 390 |
| taller_resultado_ubicaciones | 390 |

- Período de creación: septiembre de 2026 a septiembre de 2027. Incluye fechas
  futuras respecto de la fecha de carga. Son datos ficticios para desarrollo.
- Estados de las 409 OT: 386 finalizadas, 12 pendientes, 4 en reparación y
  7 liberadas. Los estados globales incluyen filas de meses anteriores al actual.
- IDs enteros importados = ID fuente + 1.000.000. Los buses se vinculan por
  número, las ciudades por código y los roles por nombre; sus IDs originales
  no se reutilizan como claves locales. Los UUID de operaciones se conservan.
- Se crean siete usuarios de referencia y un actor técnico, todos inactivos,
  sin contraseña utilizable. Los nombres de los mecánicos se conservan.
- Se omiten seis filas activas de cuadrilla que repiten exactamente otra fila
  salvo por el ID. Las asignaciones por falla se conservan completas. Si los
  duplicados difieren en otro campo, la carga falla.
- `origen=SIMULACION` no está permitido en asignaciones: se adapta a `SUPERVISOR`,
  se identifica el actor técnico y se conserva el origen original en `comentario`.
- Los eventos sin actor se identifican como `Simulación Dashboard`. Las operaciones
  y ubicaciones con actor nulo usan el actor técnico, porque la base exige actor.
  La respuesta nula de las operaciones se sustituye por metadatos de simulación.
- `descripcion_normalizada` es un campo derivado del prototipo y no es columna de
  la base; la descripción original se conserva. No se inventan comentarios,
  evidencias, participantes de evento ni transiciones de estado ausentes.
- Los triggers existentes recalculan horas de estadías y marcas `en_taller`.
  No se desactivan restricciones ni triggers durante la carga.

## Revertir

```powershell
.\.venv\Scripts\python.exe -m alembic downgrade 031_depuracion_supervision
```

El downgrade elimina únicamente los IDs del snapshot y los usuarios creados por
esta carga, en orden de dependencias. Habilita la depuración del historial solo
durante su transacción. Las marcas de los buses se recalculan y las secuencias
no retroceden. Si se agregó trabajo que referencia los datos de simulación, las
claves foráneas pueden impedir la reversión: no se eliminan esos registros en cascada.

La API local conserva sus 93 buses existentes; la simulación usa 50. Por ello
los denominadores de flota pueden diferir del prototipo, cuyo maestro tiene 50.

## Verificación del 27-10-2026

- Upgrade, downgrade a 031, verificación de los 128 usuarios y 93 buses originales,
  recarga y repetición de upgrade sin duplicados: correctos.
- `python -m pytest tests/unit/test_dashboard_simulados_migration.py tests/dashboard -q`:
  93 pruebas aprobadas. Las pruebas asíncronas requirieron ejecutarse fuera del sandbox.
- Lectura con servicios del dashboard sobre PostgreSQL local: indicadores y las
  seis series correctos; distribución de talleres 232 Temuco, 82 Santiago y 76 externos.
- `alembic check` no pasa por diferencias previas de esquema ajenas a esta revisión
  de datos: falta `taller_correcciones_visitas`, la expresión del índice
  `uq_ciudades_codigo_normalizado` difiere (`TRIM(BOTH FROM ...)` frente a `trim(...)`)
  y la restricción única de `taller_resultado_ubicaciones.operacion_id` tiene otro
  nombre. Estas diferencias no se repararon como parte de la carga.
