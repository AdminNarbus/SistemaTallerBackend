# Talleres, ciudades y ubicación de resultados

Revisión inicial: `028_talleres_resultados` (desde `027_fechas_evento_registro`). Esta funcionalidad registra en qué taller se reportó cada resultado de una falla. No crea ciclos de trabajo ni tiempos por taller.

## Catálogos

Todas las rutas usan el prefijo `/api/v1/taller`.

La migración `030_ciudades_comunas_chile` precarga 346 comunas chilenas en `ciudades`, usando el CUT oficial como `codigo`. Chile organiza oficialmente su territorio en regiones, provincias y comunas; el catálogo usa la tabla `ciudades` para que los talleres puedan seleccionar su comuna. Fuentes: [SUBDERE, Códigos Únicos Territoriales](https://www.subdere.gov.cl/documentacion/c%C3%B3digos-%C3%BAnicos-territoriales-actualizados-al-06-de-septiembre-2018) y [INE, División Político-Administrativa](https://www.ine.gob.cl/docs/default-source/geodatos-abiertos/publicaciones/division-politica-administrativa/dpa-2018/presentaci%C3%B3n.pdf?sfvrsn=ba51e191_4).

| Método y ruta | Permiso | Uso |
|---|---|---|
| `GET /ciudades` | Mecánico, supervisor, admin | Lista ciudades disponibles. |
| `POST /ciudades` | Supervisor, admin | Crea `{ "codigo": "SCL", "nombre": "Santiago" }`; responde `201` con el registro. El código se normaliza a mayúsculas y no se repite ignorando mayúsculas/minúsculas. |
| `GET /talleres` | Mecánico, supervisor, admin | Lista paginada; filtros `ciudad_id`, `tipo`, `is_activo`, `q`, `skip`, `limit`; total en `X-Total-Count`. |
| `POST /talleres` | Supervisor, admin | Crea `{ "nombre": "Maestranza Norte", "ciudad_id": 1, "tipo": "INTERNO" }`; responde `201`. |
| `PATCH /talleres/{taller_id}` | Supervisor, admin | Actualiza nombre, ciudad, tipo o `is_activo`. No admite valores nulos ni borrado físico. |

Los tipos válidos son `INTERNO` y `EXTERNO`. Se conserva una fotografía histórica del nombre, ciudad y tipo usado al registrar el resultado.

## Registrar resultado

`PATCH /api/v1/taller/{id}/detalles/{detalle_id}/check` y la ruta equivalente de supervisión `/api/v1/supervision/solicitudes/{id}/detalles/{detalle_id}/resolver` aceptan JSON o multipart. El body JSON usa:

```json
{
  "operacion_id": "d061dfb9-9b3d-4be8-8ff0-250cdb0ff72b",
  "evento_esperado_id": 1010,
  "estado": "INCOMPLETA",
  "mecanicos_ids": [42, 43],
  "taller_id": 1,
  "talleres_colaboradores_ids": [7],
  "motivo_incompleto": "Falta un componente",
  "comentario": "Se continúa mañana"
}
```

`evento_esperado_id` siempre se envía y puede ser `null` si la falla no tiene evento. El GET de la OT expone el ID vigente para formar esta expectativa. Una expectativa antigua devuelve `409`. `operacion_id` es un UUID nuevo por operación lógica; un reintento con mismo contenido devuelve la respuesta original, mientras que reutilizarlo con contenido diferente devuelve `409`. Omitir colaboradores equivale a `[]`.

Para `RESUELTA` o `INCOMPLETA`, `taller_id` es obligatorio. `PENDIENTE` registra una reapertura y no admite autores ni ubicación. La respuesta mantiene los campos existentes y agrega `evento_id`, `evento_estado_vigente_id`, `operacion_id`, autores del evento (`mecanicos_resolvieron` o `mecanicos_avance`) y `ubicacion`, que contiene el responsable, colaboradores, sus ciudades y tipos, versión, actor, fecha y motivo si corresponde.

Un supervisor/admin debe enviar `mecanicos_ids` explícitamente, aunque sea `[]`. Al reemplazar A,B por B,C, el equipo actual queda B,C y la asignación de A se desactiva preservando su historial. Un mecánico registra con la hora del servidor, requiere asignación activa y declara su equipo asignado completo. Supervisión puede indicar una fecha ISO-8601 con zona horaria, nunca futura. Mecánicos y supervisores pueden registrar `INCOMPLETA → INCOMPLETA`; solo supervisión/admin puede registrar `RESUELTA → RESUELTA`. Los demás cambios siguen las restricciones del flujo de fallas existente. Una OT finalizada debe reabrirse antes de registrar un resultado.

Puede registrarse un resultado sin autores internos si el responsable o al menos un colaborador es externo. La ubicación describe el evento de falla; una reparación externa no crea asignaciones ficticias. Registrar un resultado no cierra asignaciones restantes ni finaliza la OT.

## Completar o corregir un resultado antiguo

`POST /api/v1/taller/{id}/detalles/{detalle_id}/eventos/{evento_id}/ubicacion` es exclusivo para supervisor/admin. Ejemplo:

```json
{
  "operacion_id": "91faebdd-f9a2-48ab-af69-70bb1f5f8447",
  "ubicacion_esperada_id": null,
  "taller_id": 1,
  "talleres_colaboradores_ids": [7],
  "motivo": "Taller acreditado mediante orden de servicio"
}
```

Se puede usar para eventos `RESUELTA` o `INCOMPLETA`, incluso en una OT finalizada y con talleres desactivados. La primera anotación lleva `ubicacion_esperada_id: null`; las correcciones siguientes envían el ID de la versión actual. Una expectativa desactualizada devuelve `409`. Cada anotación agrega una versión inmutable y la respuesta `201` incluye la versión nueva. Corregir ubicación no cambia estado, autores, fecha efectiva ni asignaciones.

Las OTs anteriores sin evidencia de taller continúan sin ubicación. No se infiere ciudad o taller desde asignaciones, mecánicos ni fechas.

## Auditoría

`GET /api/v1/supervision/auditoria/buses-taller` acepta `ciudad_id`, `taller_id`, `colaborador_id` y `ambito=ACTUAL|HISTORICO|TODOS` junto con sus filtros y paginación existentes. `ACTUAL` exige la última versión de ubicación del último resultado que coincide con el estado actual de la falla; `HISTORICO` incluye versiones corregidas y resultados que ya no representan el estado actual; `TODOS` incluye cualquier ubicación anotada. El filtro se aplica mediante `EXISTS`, por lo que varias colaboraciones no duplican una OT.

## Persistencia y límites de entrega

La revisión crea `ciudades`, `talleres`, `taller_resultado_ubicaciones`, `taller_resultado_colaboradores` y `taller_resultado_operaciones`. Los resultados, autores, ubicación, comentario, adjuntos y recibo de idempotencia se guardan dentro de la transacción del resultado. Las correcciones históricas son anotaciones adicionales; no reescriben el evento. No hay endpoints de borrado de ciudad/taller ni rutas de preparación, principal, apoyo o cierre por taller.

El cliente debe enviar UUID y taller al registrar resultados nuevos. Coordinar y desplegar el cambio del cliente antes de exigir este contrato en producción.
