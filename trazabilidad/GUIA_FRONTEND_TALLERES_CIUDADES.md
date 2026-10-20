# Guía frontend: talleres, ciudades y resultados de fallas

## Para qué existe este cambio

El objetivo es responder una pregunta operativa concreta: **¿en qué taller se realizó o avanzó el trabajo de esta falla, y qué otros talleres colaboraron?** La ciudad se obtiene del taller elegido. Así se pueden consultar resultados por ciudad, taller responsable o colaborador sin inferir ubicaciones desde quién fue asignado ni crear un flujo paralelo de trabajos por taller.

La ubicación queda asociada a cada resultado de falla. Si el estado de la falla cambia, se registra otro evento. Si supervisión corrige una ubicación histórica, se añade una versión con motivo y autor; las versiones anteriores siguen disponibles. Los datos antiguos sin evidencia de taller se muestran sin ubicación.

## Flujo recomendado de pantalla

1. Cargar ciudades y talleres para poblar selectores.
2. Al abrir una OT, usar el detalle de la falla para leer `estado`, `evento_estado_vigente_id`, `ubicacion_vigente_id`, asignaciones actuales e historial.
3. Al guardar el resultado, generar un `operacion_id` UUID una sola vez y conservarlo para reintentos de esa misma acción. Enviar también el `evento_esperado_id` leído al abrir/actualizar la ficha.
4. Para un resultado `RESUELTA` o `INCOMPLETA`, pedir taller responsable y permitir cero o más colaboradores. La ciudad se muestra a partir del taller y no se envía como campo independiente.
5. Si el backend responde `409`, recargar la OT y pedir que la persona confirme el cambio antes de enviar una operación nueva con otro UUID.

No finalizar ni reabrir una OT como efecto automático del registro de resultado. El usuario conserva el flujo normal de la OT.

## Autenticación y permisos

Enviar el token habitual en `Authorization: Bearer <token>`.

- Mecánicos, supervisión y administración pueden consultar ciudades y talleres.
- Supervisión y administración pueden crear ciudades/talleres, editar talleres y corregir ubicaciones históricas.
- Un mecánico solo registra resultados si tiene asignación activa en esa falla. Registra con la hora del servidor y declara el equipo asignado completo; no puede cambiar la lista de autores.
- Supervisión/administración puede registrar resultados con o sin asignación previa, selecciona autores activos y puede indicar una fecha efectiva pasada.
- Una OT `FINALIZADA` debe reabrirse antes de registrar un resultado. La corrección de ubicación histórica sí está permitida aunque la OT esté finalizada.

Reglas de estados relevantes:

- `INCOMPLETA → INCOMPLETA`: mecánico y supervisión/administración.
- `RESUELTA → RESUELTA`: solo supervisión/administración.
- `PENDIENTE`: reapertura; no lleva autores ni ubicación.
- Para `RESUELTA` e `INCOMPLETA`, debe enviarse un taller responsable activo. Los talleres desactivados solo se aceptan al completar/corregir historia.
- Supervisión al declarar autores cambia las asignaciones actuales de esa falla para que coincidan con la lista seleccionada. Por ejemplo, A,B → B,C desactiva a A y deja a B,C como equipo actual; el historial conserva la asignación anterior de A.
- Se puede enviar `mecanicos_ids: []` si participa un taller externo (responsable o colaborador). No se crean asignaciones ficticias para el trabajo externo.

## Catálogos

Todas las rutas nuevas usan el prefijo `/api/v1/taller`.

La migración precarga 346 comunas de Chile, identificadas por el CUT oficial en `codigo`. Aunque la API las llama ciudades por el modelo actual, la fuente oficial las define como comunas; el modelo no guarda la región. La lista procede de [SUBDERE, Códigos Únicos Territoriales](https://www.subdere.gov.cl/documentacion/c%C3%B3digos-%C3%BAnicos-territoriales-actualizados-al-06-de-septiembre-2018).

### Consultar ciudades

`GET /api/v1/taller/ciudades`

Respuesta `200`:

```json
[
  { "id": 1, "codigo": "SCL", "nombre": "Santiago" }
]
```

### Crear ciudad

`POST /api/v1/taller/ciudades` — supervisión/administración.

```json
{ "codigo": "SCL", "nombre": "Santiago" }
```

Respuesta `201`: el objeto de ciudad anterior. El código se normaliza a mayúsculas y debe ser único.

### Buscar talleres

`GET /api/v1/taller/talleres?ciudad_id=1&tipo=EXTERNO&is_activo=true&q=norte&skip=0&limit=20`

Todos los filtros son opcionales. `tipo` acepta `INTERNO` o `EXTERNO`; `limit` va de 1 a 100. La respuesta es una lista y el total viene en la cabecera `X-Total-Count`.

```json
[
  { "id": 7, "nombre": "Servicio Norte", "ciudad_id": 1, "tipo": "EXTERNO", "is_activo": true }
]
```

Usar `is_activo=true` para resultados nuevos. Al mostrar historia, también pueden aparecer talleres que ahora estén desactivados, porque su snapshot conserva el nombre, ciudad y tipo originales.

### Crear y actualizar talleres

`POST /api/v1/taller/talleres` — supervisión/administración.

```json
{ "nombre": "Servicio Norte", "ciudad_id": 1, "tipo": "EXTERNO" }
```

Respuesta `201`: objeto `TallerDTO` con `id`, `nombre`, `ciudad_id`, `tipo` e `is_activo`.

`PATCH /api/v1/taller/talleres/{taller_id}` acepta uno o más campos no nulos:

```json
{ "nombre": "Servicio Norte actualizado", "is_activo": false }
```

Respuesta `200`: taller actualizado. No existe borrado físico. Si se desactiva un taller, se conserva visible en snapshots históricos.

## Registrar resultado de falla

Hay dos rutas con el mismo contrato:

- `PATCH /api/v1/taller/{solicitud_id}/detalles/{detalle_id}/check`
- `PATCH /api/v1/supervision/solicitudes/{solicitud_id}/detalles/{detalle_id}/resolver` (solo supervisión/administración)

Para JSON, enviar `Content-Type: application/json`. Ejemplo de resultado incompleto:

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

Para una resolución, cambiar `estado` a `RESUELTA`; `motivo_incompleto` ya no es necesario. Para `PENDIENTE`, enviar el mismo UUID y el evento esperado, más `estado: "PENDIENTE"`; omitir `taller_id`, colaboradores y autores.

Campos importantes:

| Campo | Uso |
|---|---|
| `operacion_id` | UUID obligatorio y único por acción lógica. Reutilizarlo solo para reintentar exactamente el mismo body y actor. |
| `evento_esperado_id` | ID de `evento_estado_vigente_id` leído desde la OT; obligatorio incluso cuando todavía no hay eventos, caso en que debe ser `null`. Protege contra guardar sobre una ficha antigua. |
| `estado` | `RESUELTA`, `INCOMPLETA` o `PENDIENTE`. También se acepta el formato legado `resuelto`, pero el cliente nuevo debe enviar `estado`. |
| `mecanicos_ids` | Supervisión/admin debe enviarlo explícitamente en resultados no `PENDIENTE`, incluso como `[]`. El mecánico puede omitirlo para usar su equipo activo completo; si lo envía, debe coincidir con ese equipo. |
| `taller_id` | ID del taller responsable; obligatorio para `RESUELTA` e `INCOMPLETA`. |
| `talleres_colaboradores_ids` | Lista opcional; si se omite equivale a `[]`. No repetir responsable ni colaboradores. |
| `fecha_cambio_estado` | Opcional, fecha ISO-8601 con zona horaria. Solo supervisión/admin; no puede ser futura. Mecánicos usan hora del servidor. |
| `motivo_incompleto` | Recomendado para explicar qué queda pendiente al registrar `INCOMPLETA`. |
| `comentario` | Comentario operativo opcional; se agrega a la bitácora de la OT. |

La respuesta es `200` y conserva campos del detalle. Ejemplo abreviado:

```json
{
  "detalle_id": 55,
  "solicitud_id": 12,
  "estado": "INCOMPLETA",
  "resuelto": false,
  "motivo_incompleto": "Falta un componente",
  "fecha_cambio_estado": "2026-10-19T14:20:00Z",
  "fecha_registro": "2026-10-19T14:20:01Z",
  "evento_id": 1011,
  "evento_estado_vigente_id": 1011,
  "operacion_id": "d061dfb9-9b3d-4be8-8ff0-250cdb0ff72b",
  "mecanicos_avance": [
    { "id": 42, "nombre": "Mecánico Uno" },
    { "id": 43, "nombre": "Mecánico Dos" }
  ],
  "mecanicos_resolvieron": [],
  "ubicacion": {
    "id": 220,
    "version": 1,
    "taller_responsable": {
      "id": 1, "nombre": "Taller Central", "ciudad": "Santiago", "tipo": "INTERNO"
    },
    "talleres_colaboradores": [
      { "id": 7, "nombre": "Servicio Norte", "ciudad": "Santiago", "tipo": "EXTERNO" }
    ],
    "registrado_por_id": 9,
    "registrado_por": "Supervisora",
    "registrado_en": "2026-10-19T14:20:01Z",
    "operacion_id": "d061dfb9-9b3d-4be8-8ff0-250cdb0ff72b",
    "motivo": null
  }
}
```

En `RESUELTA`, los autores aparecen en `mecanicos_resolvieron`; en `INCOMPLETA`, en `mecanicos_avance`. En `PENDIENTE`, la respuesta `ubicacion` y ambas listas de autores son vacías. La ficha de la OT incluye además `historial_eventos`; cada evento expone su `taller_ubicacion` y `historial_ubicaciones`.

### Reintentos y errores

- Si la red falla después de enviar, repetir exactamente el body con el mismo `operacion_id`; el backend devuelve la respuesta recibida originalmente sin duplicar evento, comentario ni adjuntos.
- El mismo UUID con otro actor, falla o contenido devuelve `409`. Para una acción distinta, generar UUID nuevo.
- `409` también indica que `evento_esperado_id` quedó obsoleto. Recargar la OT y resolver el conflicto antes de volver a enviar.
- `403`: rol, asignación o transición no permitidos.
- `404`: OT, falla, mecánico o taller inexistente/no relacionado.
- `422`: payload incompleto o inválido (por ejemplo, sin taller en un resultado).
- `401`: token ausente o inválido.

El endpoint no cierra automáticamente asignaciones restantes ni finaliza la OT. Al declarar autores, supervisión ajusta el equipo actual de esa falla a esos autores; el historial de asignaciones conserva quién estuvo antes.

### Multipart con fotos

Las mismas rutas aceptan `multipart/form-data` si se adjuntan fotos mediante el campo repetido `fotos`. Las listas se envían repitiendo la clave para cada ID. Ejemplo con `FormData`:

```javascript
const form = new FormData();
form.append("operacion_id", crypto.randomUUID());
form.append("evento_esperado_id", String(eventoEsperadoId));
form.append("estado", "RESUELTA");
form.append("taller_id", String(tallerId));
form.append("mecanicos_ids", String(mecanico1Id));
form.append("mecanicos_ids", String(mecanico2Id));
form.append("talleres_colaboradores_ids", String(tallerColaboradorId));
form.append("comentario", "Reparación verificada");
form.append("fotos", archivo);

await fetch(url, {
  method: "PATCH",
  headers: { Authorization: `Bearer ${token}` },
  body: form
});
```

No establecer manualmente `Content-Type` al enviar `FormData`; el navegador agrega el boundary multipart. Los campos de fecha y UUID se envían como texto; las claves de listas se repiten. El contenido de adjuntos también forma parte del fingerprint de idempotencia: al reintentar, conserva los mismos archivos.

## Completar/corregir ubicación histórica

`POST /api/v1/taller/{solicitud_id}/detalles/{detalle_id}/eventos/{evento_id}/ubicacion` — solo supervisión/administración. Se usa para resultados antiguos sin ubicación o para corregirla; también funciona en una OT finalizada y admite talleres hoy desactivados.

```json
{
  "operacion_id": "91faebdd-f9a2-48ab-af69-70bb1f5f8447",
  "ubicacion_esperada_id": null,
  "taller_id": 1,
  "talleres_colaboradores_ids": [7],
  "motivo": "Taller acreditado mediante orden de servicio"
}
```

`ubicacion_esperada_id` es `null` para la primera anotación y luego el ID de la versión actual. El frontend debe leerlo desde `ubicacion_vigente_id` del detalle o desde el ID de la última entrada de `historial_ubicaciones` del evento. Si ya no coincide, el backend responde `409` y el cliente debe recargar antes de corregir.

Respuesta `201`: `UbicacionEventoDTO`, con la misma estructura `ubicacion` del ejemplo anterior y `version` incrementada. El motivo, quién corrigió y cuándo deben mostrarse en la historia. Esta operación no cambia estado, autores, fecha efectiva ni asignaciones.

## Consultar historia y filtrar auditoría

Para mostrar el estado y ubicación vigentes, leer el detalle de la OT. Cada falla contiene:

- `evento_estado_vigente_id`: enviarlo como `evento_esperado_id` en el siguiente resultado.
- `ubicacion_vigente_id`: ID requerido al corregir la ubicación.
- `ubicacion`: ubicación del resultado vigente, o `null` si no hay evidencia registrada.
- `historial_eventos`: cronología de estados; cada entrada incluye actor, fechas, autores, ubicación y correcciones.
- `historial_asignaciones`: asignaciones actuales e históricas. No usar esta lista para inferir dónde se trabajó.

`GET /api/v1/supervision/auditoria/buses-taller` admite los filtros:

```text
?ciudad_id=1&taller_id=1&colaborador_id=7&ambito=ACTUAL&skip=0&limit=20
```

`ambito` acepta `ACTUAL`, `HISTORICO` o `TODOS`; por omisión se consultan todas las ubicaciones. La respuesta es la lista de resumen de OTs y `X-Total-Count` informa el total. Un mismo bus/OT no debe duplicarse por tener varios colaboradores.

## Notas para el rollout del cliente

El contrato de resultados ahora requiere `operacion_id`, `evento_esperado_id` y taller para estados `RESUELTA` e `INCOMPLETA`. Desplegar el cliente que envía estos campos junto con el backend antes de depender de ellos en producción. Los registros anteriores sin ubicación son válidos y deben presentarse como “sin ubicación registrada”, no completarse automáticamente.
