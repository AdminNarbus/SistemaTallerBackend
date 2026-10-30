# Pauta preventiva: contrato de integración

Implementación local actualizada el 30 de octubre de 2026. No desplegada por esta tarea.
Todas las rutas usan el prefijo `/api/v1` y `Authorization: Bearer <token>`.
`{id}` es el ID numérico de la solicitud/OT; `item_id` es el ID del catálogo, no su posición.

## Abrir el detalle de una OT en supervisión

`GET /api/v1/supervision/solicitudes/{id}` — SUPERVISOR o ADMIN.

La ficha conserva sus demás campos y sustituye el listado `pauta_respuestas` por:

```json
{
  "pauta_completada": false,
  "pauta_resumen": {"revisadas": 6, "total": 10}
}
```

Mostrar `6 / 10 revisadas`. El total se calcula desde el catálogo activo, no se fija en el cliente.
`revisadas` cuenta puntos con respuesta `OK`, `DEFECTO` o `NO_APLICA`: completar la pauta
significa responderla, no que todos los puntos estén en buen estado. Un catálogo vacío da
`0 / 0` y `pauta_completada=false`.

**Cambio de contrato:** solo el GET del detalle de supervisión omite `pauta_respuestas`.
Los endpoints anteriores de taller y las respuestas de otras acciones conservan su contrato.
Para abrir el desglose desde supervisión, consumir el GET siguiente.

## Consultar todos los puntos de una OT

`GET /api/v1/supervision/solicitudes/{id}/pauta` — SUPERVISOR o ADMIN.

Devuelve todos los puntos activos, ordenados por `orden` e ID, incluidos los pendientes:

```json
{
  "solicitud_id": 35,
  "resumen": {"revisadas": 1, "total": 2},
  "puntos": [
    {
      "id": 1, "categoria": "General", "item": "Punto 1", "orden": 1,
      "is_active": true, "revisado": true,
      "respuesta": {
        "id": 80, "solicitud_id": 35, "item_id": 1,
        "item_categoria": "General", "item_nombre": "Punto 1",
        "estado": "DEFECTO", "observacion": "Fuga",
        "mecanico_id": 2, "mecanico_nombre": "Pedro Mecanico",
        "mecanicos_ids": [2, 3],
        "mecanicos": [{"id": 2, "nombre": "Pedro Mecanico"}, {"id": 3, "nombre": "Carlos Mecanico"}],
        "fecha_registro": "2026-10-29T18:00:00Z"
      }
    },
    {
      "id": 2, "categoria": "General", "item": "Punto 2", "orden": 2,
      "is_active": true, "revisado": false, "respuesta": null
    }
  ]
}
```

`respuesta.mecanicos_ids` y `respuesta.mecanicos` identifican a todos los ejecutores del punto.
Los campos singulares `mecanico_id`/`mecanico_nombre` se conservan por compatibilidad y
representan al revisor de menor ID; para mostrar todos los revisores usar la lista.
El supervisor/administrador que registra el cambio se obtiene
del token y aparece como autor del comentario en la bitácora, no como mecánico revisor.
La fecha es la del registro/corrección, no una fecha de ejecución declarada por el cliente.

## Obtener la lista para el selector de mecánicos

Usar el endpoint existente, con el token del supervisor/administrador:

```http
GET /api/v1/auth/mecanicos?q=&skip=0&limit=20
Authorization: Bearer <token>
```

- Devuelve un array de usuarios de rol `MECANICO` activos. No requiere filtrar roles en frontend.
- `q`: búsqueda opcional por nombre, apellido o username; vacío lista los resultados por páginas.
- `skip`: desplazamiento, inicialmente 0; `limit`: tamaño de página, por defecto 20, máximo 100.
- `X-Total-Count`: cabecera con el total de coincidencias. Aumentar `skip` para obtener más páginas;
  la primera respuesta no necesariamente contiene todos los mecánicos.
- `exclude_id`: filtro opcional existente; para este selector se puede omitir.
- Alias equivalente: `GET /api/v1/auth/mecanicos/buscar` con los mismos parámetros.

Ejemplo abreviado de respuesta (el DTO también incluye otros datos personales):

```json
[
  {"id": 2, "nombre": "Pedro", "apellido": "Mecanico", "nombre_completo": "Pedro Mecanico", "rol": "MECANICO", "is_active": true},
  {"id": 3, "nombre": "Carlos", "apellido": "Mecanico", "nombre_completo": "Carlos Mecanico", "rol": "MECANICO", "is_active": true}
]
```

Mostrar `nombre_completo` como etiqueta y guardar `id` como valor de la opción. El selector
debe permitir seleccionar varios y enviar esos IDs en `mecanicos_ids` del punto.
Cada punto puede tener un grupo distinto; una selección para toda la pauta se copia en cada punto enviado.
No se exige que el mecánico esté asignado previamente a una falla de la OT.

## Registrar, corregir y desmarcar revisiones

`PATCH /api/v1/supervision/solicitudes/{id}/pauta` — SUPERVISOR o ADMIN.

```json
{
  "puntos": [
    {"item_id": 1, "estado": "OK", "mecanicos_ids": [2, 3], "observacion": "Revisado en conjunto"},
    {"item_id": 2, "estado": "DEFECTO", "mecanicos_ids": [3], "observacion": "Fuga detectada"},
    {"item_id": 3, "estado": "NO_APLICA", "mecanicos_ids": [2, 3]},
    {"item_id": 4, "estado": null}
  ]
}
```

- `OK`: revisión conforme.
- `DEFECTO`: revisión realizada con defecto.
- `NO_APLICA`: punto evaluado que no corresponde; cuenta como respondido.
- `null`: aún no revisado; elimina la respuesta vigente y devuelve el punto a pendiente.
- `estado` es obligatorio, incluso cuando se envía `null`.
- `mecanicos_ids` debe contener al menos un ID positivo, sin repetidos, de mecánicos activos
  cuando `estado` es `OK`, `DEFECTO` o `NO_APLICA`, también al corregir.
- La lista reemplaza completamente la selección del punto: `[2, 3]` seguido de `[3]` retira al 2.
  Varios revisores siguen contando como un solo punto revisado.
- Por compatibilidad se acepta `mecanico_id: 2` como selección individual. No enviar ambos campos.
- Para desmarcar, enviar `estado: null` y omitir revisores y observación; elimina todas las asociaciones del punto.
- No enviar el ID del supervisor como revisor. El autor de la gestión se obtiene del token;
  no existe un campo editable `supervisor_id`/`actor_id` en el cuerpo.
- Solo se modifican los puntos enviados. Omitir un punto conserva su respuesta.
- Enviar `observacion` con una respuesta reemplaza la anterior; omitirla la deja en `null`.
- Un punto pendiente no admite observación ni mecánico. No se aceptan IDs repetidos, listas vacías,
  estados desconocidos ni campos adicionales.
- La operación es atómica: un punto inexistente/inactivo o un revisor inválido rechaza todo el lote.
- Cada operación registra al supervisor/administrador como autor, los puntos, estados y
  mecánicos seleccionados en la bitácora `CHECKLIST`, actualiza
  `fecha_actualizacion` de la OT y emite el evento `work_order` / `checklist.changed`.
- No cambia automáticamente el estado de la OT ni resuelve fallas asociadas.
- Se mantiene el comportamiento existente respecto de OT liberadas/finalizadas:
  no se agrega una restricción por estado para corregir su pauta.

Respuesta `200`: la misma estructura del GET, con resumen y todos los puntos actualizados.
Tras guardar, actualizar el indicador del detalle usando `resumen` de esta respuesta.

## Endpoints existentes

| Método | Ruta | Permiso | Contenido |
|---|---|---|---|
| GET | `/api/v1/formularios/pauta/items` | Usuario autenticado | Catálogo de ítems activos |
| GET | `/api/v1/formularios/pauta/solicitudes/{id}` | Usuario autenticado | Respuestas guardadas y resumen completo |
| POST | `/api/v1/formularios/pauta/solicitudes/{id}` | MECANICO o ADMIN | Registrar/actualizar respuestas por lote |
| GET | `/api/v1/taller/pauta/items` | Usuario autenticado | Catálogo compatible de taller |
| GET | `/api/v1/taller/{id}/pauta` | Usuario autenticado | Respuestas y resumen compatible |
| POST | `/api/v1/taller/{id}/pauta` | MECANICO o ADMIN | Registro compatible |

También existen los alias ocultos de formularios
`GET/POST /api/v1/formularios/solicitudes/{id}/pauta`.

Cuerpo de los POST existentes:

```json
{"respuestas": [{"item_id": 1, "estado": "OK", "observacion": "Conforme"}]}
```

Su respuesta contiene `total_items`, `respondidos`, `pendientes`, `completado`,
`items_con_defecto` y `respuestas`. Solo lista respuestas guardadas; para todos los puntos
desde supervisión usar el nuevo GET. Estos POST no permiten devolver un punto a pendiente.

### Cuando un mecánico marca la pauta desde su flujo

Los POST existentes guardan **solo al usuario autenticado**, aunque tenga compañeros activos
en la misma OT. No copian automáticamente la cuadrilla. Si luego se actualiza un punto que
tenía varios ejecutores desde uno de esos POST, el conjunto vigente pasa a ser solo el autor
de esa nueva revisión. La gestión anterior permanece en la bitácora.
La selección de varios ejecutores está disponible en el PATCH de supervisión.

## Migración necesaria para varios ejecutores

Esta ampliación requiere `034_pauta_mecanicos` (`alembic upgrade head`) antes de ejecutar el
código nuevo. Crea la tabla de asociación `taller_solicitud_pauta_mecanicos` y copia los revisores
singulares existentes. No se ha aplicado en Neon ni se ha desplegado por esta tarea.
Verificación del 30 de octubre: la base local `narbus_taller_db` en localhost:5432 ya estaba
en `034_pauta_mecanicos`; el upgrade confirmó ese estado, con 7 asociaciones y ningún
revisor previo sin vínculo. No se accedió a Neon. El check local detecta diferencias ajenas
a esta tabla, registradas en `trazabilidad/auditoria/20261030_local_alembic_check.txt`.
El downgrade bloquea la reversión si existen respuestas con varios ejecutores para evitar
perder asociaciones. Las revisiones siguen siendo únicas por OT/punto; el avance no se multiplica.

## Errores de las nuevas rutas

| Código | Significado |
|---|---|
| 401 | Token ausente, inválido o expirado |
| 403 | Rol distinto de SUPERVISOR o ADMIN |
| 404 | OT inexistente; en PATCH, ítem inexistente o inactivo |
| 422 | Cuerpo inválido, ítem repetido, revisor ausente/inexistente/inactivo/de otro rol, o punto pendiente con observación/mecánico |

Los errores mantienen el formato centralizado `{"error": {"code": "...", "message": "...", "detail": null}}`.
Swagger documenta los nuevos DTOs y las rutas al ejecutar esta versión del backend.
