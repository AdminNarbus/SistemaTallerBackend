# API pública de taller

## Solicitudes y órdenes de trabajo

### Endpoint

```http
GET https://sistematallerfront-100590754321.southamerica-east1.run.app/api/v1/publica/solicitudes
```

### Payload

No requiere parámetros ni cuerpo.

### Respuesta

HTTP 200: arreglo completo de solicitudes y OT, ordenado por `id`. Si no hay solicitudes, devuelve `[]`.

```json
[
  {
    "id": 12,
    "n_bus": "105",
    "es_ot": true,
    "estado": "EN_REPARACION",
    "descripcion_general": "Revisión de frenos",
    "fecha_creacion": "2026-11-02T10:00:00Z",
    "fecha_actualizacion": "2026-11-02T12:00:00Z"
  }
]
```

| Campo | Descripción |
|---|---|
| `id` | Identificador de la solicitud. |
| `n_bus` | Número del bus. |
| `es_ot` | `true` si es una OT; `false` si aún no lo es. |
| `estado` | `PENDIENTE`, `EN_REPARACION`, `LIBERADO` o `FINALIZADO`; `null` si no es OT. |
| `descripcion_general` | Descripción general; puede ser `null`. |
| `fecha_creacion` | Fecha y hora de creación en formato ISO 8601. |
| `fecha_actualizacion` | Fecha y hora de actualización en formato ISO 8601; puede ser `null`. |

La cabecera `X-Total-Count` contiene la cantidad de solicitudes devueltas.

## Buses en taller

### Endpoint

```http
GET https://sistematallerfront-100590754321.southamerica-east1.run.app/api/v1/publica/buses-en-taller
```

### Payload

No requiere cuerpo. Acepta estos parámetros opcionales en la URL:

| Parámetro | Valor por defecto | Valores permitidos | Descripción |
|---|---:|---:|---|
| `skip` | `0` | `0` o mayor | Cantidad de buses que se omiten. |
| `limit` | `50` | `1` a `100` | Cantidad máxima de buses devueltos. |

Ejemplo: `?skip=0&limit=50`. Para la siguiente página: `?skip=50&limit=50`.

### Respuesta

HTTP 200: arreglo de buses cuyo `en_taller` es `true`, ordenados por `id`. Si no hay resultados, devuelve `[]`.

```json
[
  {
    "id": 1,
    "n_bus": "105",
    "patente": "ABCD12",
    "marca": "Marca",
    "modelo": "Modelo",
    "en_taller": true
  }
]
```

`id` identifica el bus; `n_bus`, `marca` y `modelo` pueden ser `null`. `patente` identifica su matrícula y `en_taller` indica su presencia en taller.

La cabecera `X-Total-Count` contiene el total de buses en taller, incluidos los que estén en otras páginas. Un `skip` o `limit` inválido devuelve HTTP 422.
