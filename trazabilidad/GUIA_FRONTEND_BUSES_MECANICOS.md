# Buses y registro de fallas para mecánicos

## Lista unificada

`GET /api/v1/taller/buses` requiere token de `MECANICO` o `ADMIN`.

Parámetros: `skip=0`, `limit=20` (máximo 100), `q` (búsqueda literal por número o patente, máximo 100 caracteres), `solo_activos=true`.

Devuelve una fila por bus y su OT vigente, si existe. El orden se aplica en SQL antes de paginar:

1. OT `REPORTADO`, `PENDIENTE` o `EN_REPARACION`.
2. OT `LIBERADO`.
3. Sin OT vigente; incluye buses que únicamente tienen OT `FINALIZADO`.

Dentro de cada grupo se ordena por `n_bus` y `bus_id`. Las OT antiguas sin `bus_id` se reconocen por su número de bus, sin distinguir mayúsculas ni espacios exteriores. Se prefiere una OT vinculada por ID si también hay una coincidencia antigua por número.

```json
[
  {
    "bus_id": 51,
    "n_bus": "351",
    "patente": "ABCD12",
    "marca": "Scania",
    "modelo": "K400",
    "en_taller": true,
    "is_active": true,
    "ot": {
      "id": 12,
      "estado": "EN_REPARACION",
      "fecha_actualizacion": "2026-10-29T12:00:00Z",
      "numero_fallas_pendientes": 3
    }
  }
]
```

`ot` es `null` si no hay una OT vigente. `numero_fallas_pendientes` cuenta fallas `PENDIENTE` e `INCOMPLETA`, tengan asignación o no. `en_taller` indica ubicación física y no reemplaza el estado de la OT.

La cabecera `X-Total-Count` contiene el total filtrado, incluso si la página solicitada está vacía. El listado y su total se resuelven en una consulta SQL. `Cache-Control: no-store` evita conservar una clasificación anterior al reporte.

## Añadir una falla desde un bus

`POST /api/v1/taller/buses/{bus_id}/fallas`, con token de `MECANICO` o `ADMIN`:

```json
{
  "nombre": "Fuga de aceite",
  "autoasignar": false
}
```

También admite `descripcion_personalizada`, `falla_nombre`, `falla_id`, `categoria_id` y `categoria_nombre`, igual que los detalles de reporte. Debe existir un texto de falla o un `falla_id` válido. Si se indica categoría junto a una falla de catálogo, ambas deben coincidir y estar activas.

| Situación del bus | `autoasignar: false` o campo omitido | `autoasignar: true` |
| --- | --- | --- |
| Sin OT vigente | Crea OT `PENDIENTE` y registra falla sin asignar | Crea OT y pasa a `EN_REPARACION`, asignando la nueva falla al reportante |
| OT pendiente, reportada o en reparación | Añade la falla y conserva estado/equipo | Añade y asigna únicamente la nueva falla; OT `EN_REPARACION` |
| OT liberada | Añade la falla y conserva `LIBERADO` | Reutiliza esa OT, pasa a `EN_REPARACION` y registra el reingreso |
| Solo OT finalizadas | Crea una nueva OT, preservando el historial cerrado | Crea una nueva OT y comienza su atención |

Reportar sin autoasignación no registra un ingreso físico ni cambia `bus.en_taller`. Autoasignarse asegura el ingreso al taller y una estadía abierta, sin duplicarla si ya existe.

No se admite seleccionar otro mecánico, declarar la falla resuelta ni modificar el estado mediante este payload. Para las acciones administrativas se mantienen los endpoints de supervisión.

La respuesta es `201` con `SolicitudDTO`, tanto si se creó la OT como si se reutilizó una existente: siempre se creó una nueva falla. El frontend debe utilizar el `id` devuelto, que puede corresponder a una OT creada por otro reporte concurrente. La creación de OT, falla, autoasignación, estadía e historial se confirman juntas o se revierten juntas. Después del commit se emite `resource.changed` de `work_order` con acción `created` o `updated`.

Actualizar la ficha con la respuesta e invalidar/refrescar el listado paginado, ya que el bus puede cambiar de grupo. No es necesario consultar el catálogo y las tres listas por separado.

Errores: `401` sin sesión, `403` para conductor/supervisor, `404` si el bus no existe, `422` para un bus dado de baja, una falla vacía, catálogos inválidos o campos no admitidos. La creación general de solicitudes conserva sus permisos anteriores; el mecánico crea OT únicamente como parte del reporte de una falla al bus.
