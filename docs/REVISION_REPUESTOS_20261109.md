# Revisión completa de repuestos por falla

Fecha: 2026-11-09. Resultado: sin fallos pendientes en el alcance probado.

## Resultado y correcciones

La API de catálogo, registro, consulta y anulación fue revisada contra el plan de implementación. Se verificaron 162 casos: 42 de repuestos y 120 de regresión relacionada.

| Hallazgo | Corrección y evidencia |
| --- | --- |
| Editar `/repuestos/0` podía crear un artículo porque el servicio evaluaba el ID como booleano. | IDs de ruta estrictamente positivos y selección de edición con `is not None`. Prueba confirma 422 y cero artículos creados. |
| Una anulación recargada desde SQLite perdía la zona UTC respecto de su recibo original. | DTO normaliza fecha de registro y anulación a UTC. Pruebas comparan evidencia de anulaciones repetidas y recibos. |
| El servicio solo revisaba actividad del usuario; no contrastaba su rol actual con la sesión antes de devolver recibos o mutar. | Se valida usuario activo, rol permitido y coincidencia con sesión. Pruebas unitarias con repositorio simulado y pruebas API de roles. |
| Tomar inicialmente una solicitud aprobaba su cabecera pero dejaba las fallas iniciales pendientes de revisión. | Aprobación inicial coordinada con las fallas. La asignación selectiva limita el alcance a sus IDs; una OT ya aceptada no aprueba reportes posteriores al volver a tomarse. |
| Pruebas anteriores creaban fallas operativas sin establecer su revisión. | Se preparan fallas aprobadas en pruebas de consumos y se agregan casos explícitos de rechazo sin revisión. |

## Cobertura comprobada

- Catálogo: creación, edición, códigos con ceros iniciales, espacios exteriores, duplicados, baja lógica, búsqueda por código/nombre/parte y paginación con total.
- Acceso: supervisor y administrador, mecánico asignado, mecánico ajeno, conductor, usuario inactivo, acceso anónimo y VISUAL de solo lectura.
- Contexto: falla personalizada, pertenencia a OT, solicitud sin aceptar, revisión pendiente, OT liberada, falla resuelta y lectura de OT finalizada.
- Consumo: cantidades positivas fraccionarias exactas; rechazo de cero, negativos, no finitos, exceso de precisión y desbordamiento.
- Evidencia: autor obtenido de sesión, snapshots del catálogo, unidad histórica, contexto de OT/bus, bitácora y protección contra borrado incluso después de anular.
- Correcciones: cambio de cantidad mediante anulación y nuevo registro; motivo obligatorio; mecánico solo anula sus propios registros; primera anulación conserva autor, fecha y motivo.
- Idempotencia: mismo UUID, UUID nuevo para consumo ya vigente, contenido incompatible, reintento histórico después de anular y después de cerrar.
- Atomicidad: un fallo de integridad revierte consumo, comentario y recibo; no emite notificación.
- Notificaciones: una por alta/anulación real, ninguna nueva en reintentos; las rutas no duplican eventos mediante el adaptador HTTP legado.
- Ausencia de efectos colaterales: consumo no resuelve falla, no quita `falta_repuesto` ni modifica el estado liberado de la OT.

## PostgreSQL real y Alembic

Se utilizó un clúster PostgreSQL 16 temporal en 127.0.0.1, independiente de la base de la aplicación, que se detuvo y eliminó al finalizar.

- Migración 038: upgrade, downgrade y nuevo upgrade.
- Comparación de las dos tablas creadas por la migración contra `Base.metadata`, incluyendo tipos y defaults: sin diferencias.
- CHECK de cantidades, precio/IVA y datos de anulación; FK restrictivas a detalle, artículo y usuario; índice único parcial de consumo vigente.
- Dos transacciones simultáneas con el mismo UUID dejan un consumo y una entrada de bitácora.
- Dos UUID distintos simultáneos para el mismo consumo tampoco duplican su alta.
- Anulaciones simultáneas conservan una única evidencia y comentario.
- Registro que espera el cierre de otra transacción observa `FINALIZADO` y se rechaza.
- Alembic conserva una sola cabeza: `041_revision_fallas`.

## Ejecución final

Entorno `ENVIRONMENT=dev_local`, `STORAGE_PROVIDER=local`, `DATABASE_URL=sqlite+aiosqlite:///:memory:`. Las pruebas PostgreSQL construyen su URL exclusivamente a partir del puerto del clúster temporal.

```powershell
venv/Scripts/python.exe -m pytest tests/integration/test_repuestos_api.py tests/integration/test_repuestos_revision.py tests/unit/test_repuesto_service.py tests/migrations/test_repuestos_migration.py tests/migrations/test_repuestos_postgres_runtime.py -q --tb=short --show-capture=no
# 42 passed, 11 warnings in 30.42s

venv/Scripts/python.exe -m pytest tests/integration/test_taller_api.py tests/integration/test_supervision_api.py tests/integration/test_fase4_checks_pauta_y_liberacion.py tests/integration/test_bitacora_completa_y_avance_pendiente.py tests/integration/test_revision_fallas.py tests/integration/test_aprobacion_solicitudes.py tests/unit/test_taller_service.py tests/unit/test_supervision_depuracion_fallas_y_fotos.py tests/unit/test_realtime.py -q --tb=short --show-capture=no
# 120 passed in 62.80s
```

Las 11 advertencias corresponden al alias HTTP 422 de Starlette utilizado en los handlers existentes; no son fallos funcionales de repuestos. `git diff --check` pasó.

## Límites de la confirmación

La confirmación corresponde al backend local y al PostgreSQL desechable. No se desplegó, no se aplicaron migraciones a bases externas y no se verificó el frontend. El catálogo continúa siendo informativo: no controla ni descuenta stock. Las pruebas de concurrencia cubren los escenarios descritos, sin constituir una prueba de carga sostenida.


## Verificación posterior en navegador integrado

Se probó manualmente el frontend local `http://localhost:5173` (ProtoNeumaticos), con sesión de administrador existente y API local mediante el proxy de Vite.

- Búsqueda de catálogo por código y validación de campos obligatorios: correctas.
- Creación y edición de `QA-CHAT-20261109`: correctas; artículo desactivado al terminar para evitar su uso accidental.
- Registro de `1.2345 UN` en OT 8 liberada, falla 57: correcto (registro 4); cantidad, autor y contexto visibles.
- Anulación con motivo obligatorio: correcta; evidencia persistente después de recargar. El consumo de ensayo quedó anulado.
- Bitácora conserva alta y anulación. OT 8 permanece LIBERADO.
- OT 7 FINALIZADO: modal de repuestos consultable sin formulario de alta.
- Evidencia: `.tmp/repuestos-ui-chat.png`. Se dejó la pestaña abierta con el historial de la prueba.

Esta sesión visual cubrió administrador en escritorio. No se cambió de sesión a mecánico/conductor ni se verificaron dispositivos móviles; sus permisos permanecen cubiertos por las pruebas API anteriores. No se modificó código del frontend durante esta comprobación.
