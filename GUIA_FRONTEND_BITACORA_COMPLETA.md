# Cierre de cuadrilla y avances únicos por falla

Contrato actualizado el 29 de octubre de 2026. El código está corregido localmente;
todavía no se ha desplegado.

## Terminar avance cierra toda la cuadrilla

`POST /api/v1/taller/{id}/terminar-avance` cierra **todas las asignaciones y
presencias activas de esa OT**, aunque sus integrantes trabajen en fallas distintas.
El ejecutor debe tener asignación o presencia activa en la OT.

```json
{"comentario": "Falta rotor corto; queda pendiente para el siguiente turno"}
```

`detalles_ids` se conserva para clientes existentes, pero **no limita el cierre**.
Si se envía una selección parcial de la misma OT, se cierra igualmente toda la
cuadrilla. Un ID que no pertenece a la OT provoca 422 sin modificar datos.

Se calculan las duraciones, se mantiene el estado de cada falla y la OT pasa a
`PENDIENTE`. Una falla pendiente no se marca incompleta ni resuelta por terminar
el avance. La nota se registra como un único mensaje global `ENTREGA_TURNO`.

La respuesta devuelve la ficha con la bitácora completa. Antes omitía los mensajes
anteriores en esa respuesta, aunque seguían guardados en la base.

## El backend entrega un solo avance por falla

En `GET /api/v1/taller/{id}` y en la respuesta de `terminar-avance`:

- Chat general: mostrar directamente `comentarios[]`, sin filtrar tipos.
- Avances de una falla: mostrar directamente `detalles[].historial_avances[]`.
  El backend ya entrega una sola entrada por avance, con ID, autor y fecha originales.
- `historial_asignaciones[]` conserva tiempos y participantes. Cuando una nota
  pertenece a un avance identificado, devuelve `comentario=null` y
  `comentario_avance_id` apuntando al mensaje original. No repite su texto.

Ejemplo abreviado del caso real:

```json
{
  "detalles": [{
    "id": 20,
    "historial_avances": [{
      "id": 575,
      "usuario_id": 145,
      "usuario_nombre": "Luis Linares",
      "tipo": "ENTREGA_TURNO",
      "fecha_registro": "2026-10-28T13:27:26.841575Z",
      "comentario": "Avance: Luis Linares y Juan Ferrada: ... Se debe cambiar reparación Bombin puerta cabina ..."
    }],
    "historial_asignaciones": [{
      "id": 220,
      "mecanico_id": 146,
      "comentario": null,
      "comentario_avance_id": 575
    }, {
      "id": 224,
      "mecanico_id": 145,
      "comentario": null,
      "comentario_avance_id": 575
    }]
  }]
}
```

El frontend no necesita agrupar ni deduplicar estas notas. Debe consumir la lista
`historial_avances` para el historial de avances de la falla.

La normalización usa el instante exacto de cierre de asignación y el mensaje
global de esa OT, comprobando su nota. No fusiona mensajes solo porque tengan el
mismo texto. Si la evidencia histórica es ambigua, mantiene la nota original sin
inventar autor ni fecha. Los registros almacenados no se alteran por esta lectura.

No concatenar al chat general los historiales de todas las fallas: el mismo avance
puede pertenecer a varias fallas y está representado una sola vez en `comentarios`.
Usar el ID de comentario para integrar actualizaciones; `POST /comentarios` lo
devuelve como `comentario_id`.

## Verificación del caso de Juan Ferrada

La OT 7 tiene una nota de cierre compartida por cuatro fallas y dos mecánicos.
Las asignaciones 217–224 empezaron el 27 de octubre a las 18:19:45, hora de Santiago,
y terminaron el 28 de octubre a las 10:27:26. La nota completa pertenece al comentario
global 575, registrado por Luis Linares al cerrar el equipo el día 28.

Comprobación de solo lectura con el nuevo mapper: un mensaje global 575, un avance
575 por cada una de las fallas 20, 21, 22 y 251, y cero copias de su texto en las
asignaciones de la respuesta. La fecha de inicio y el mecánico de una asignación
no se usan como autor y fecha del mensaje.

## Alta de bus y solicitudes antiguas

`POST /api/v1/buses` genera `id` en la base y lo devuelve. Ahora también vincula,
en la misma transacción, las solicitudes con `bus_id=null` del mismo número
normalizado. Estas solicitudes pasan a aparecer en el listado de mecánicos.

El caso concreto del número 1 proviene de una carga artificial del 7 de octubre
(AV-0122), que creó la OT 35 sin bus de catálogo. No es un fallo de generación de
ID del endpoint. Su reparación crea un registro explícitamente ficticio con
patente `TEST-BUS-1` e ID autogenerado; nunca usa el ID interno 1, que pertenece
al bus real 354. Tras autorización expresa del usuario para la prueba temporal
en producción, la reparación fue aplicada: **bus_id=51**, número 1, OT 35 vinculada.
La lectura del listado confirmó que aparece en la primera página para mecánicos.

Validación: 114 pruebas locales aprobadas. El código de bitácora sigue sin
desplegar. La única reparación aplicada en la base fue el alta autorizada del
vehículo ficticio ID 51 y su vínculo con la OT 35; la comprobación posterior
fue de solo lectura.

Integración frontend: no hace falta implementar filtros ni deduplicación de
avances. Si la pantalla usa las notas de `historial_asignaciones`, debe pasar a
mostrar `historial_avances`. El chat global debe seguir usando `comentarios`.
La solución completa requiere desplegar el backend y ajustar esa fuente donde
corresponda; no se inspeccionó ni modificó el repositorio frontend.
