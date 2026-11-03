# Dashboard: contrato de integración frontend

Revisión documental: 27 de octubre de 2026. Contrato implementado, versión 1.

Los ejemplos usan rutas relativas al servidor backend. Configurar su origen en el frontend; no copiar credenciales de base de datos al navegador. OpenAPI del backend: `/docs` y `/openapi.json`.

## Alcance y actualización

Módulo backend `app/modules/dashboard`, bajo `/api/v1/dashboard`. Todos los endpoints son GET sin body y requieren `Authorization: Bearer <access_token>` con rol `SUPERVISOR` o `ADMIN`.

Cada petición consulta la base configurada del backend y calcula en SQL. El módulo reutiliza `get_db`; no incorpora credenciales ni una conexión especial a Neon. La conexión operacional del entorno debe apuntar a la base autorizada. No consume archivos del prototipo, no guarda resultados ni crea tablas, snapshots, tareas diarias o canales de tiempo real.

El cliente consulta al entrar, cambiar filtros, elegir una marca/bus/hito, actualizar o exportar. Una OT nueva aparece en la siguiente consulta; una pantalla abierta no cambia sin pedir datos. Actualizar conserva los filtros y repite las consultas necesarias. Evitar pedir paneles ocultos; cancelar/descartar respuestas de filtros anteriores si el usuario cambia la selección rápidamente.

Los endpoints responden `Cache-Control: no-store`. La memoria del cliente contiene únicamente la vista cargada y su selección; no constituye almacenamiento operacional.

## Envoltorio, fechas y paginación

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-26T18:00:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {}
}
```

`generado_en` es la fecha de consulta; `fecha_referencia_datos` es el último día local de creación de OT de la base, o null si no hay OT. No es un snapshot. Antigüedad mantiene la regla del prototipo: compara con el final de ese día, aunque sea anterior a la fecha de consulta. Fechas devueltas en UTC, agrupaciones en Santiago y semanas desde lunes. Duraciones en horas corridas entre instantes absolutos; no equivalen a permanencia física acumulada.

Todas las colecciones usan:

```json
{"items": [], "total": 0, "skip": 0, "limit": 20}
```

`skip >= 0`, `1 <= limit <= 100`, predeterminado 20. `total` y `X-Total-Count` representan todo el resultado, incluso cuando una página está vacía. Grupos fijos pueden mostrar cantidad cero. Rankings contienen como máximo cinco buses, aunque se solicite un límite mayor. Cada respuesta tiene un `response_model` tipado y las variantes aparecen en OpenAPI.

Los ejemplos de este documento son ilustrativos, no datos reales. Los IDs, nombres y cantidades no deben usarse como datos operacionales. Cada ejemplo de endpoint incluye el payload de ruta/query y la respuesta completa `metadata` + `data`. Ausencias = null, cantidades reales = 0, porcentaje sin denominador = null; el cliente muestra `-` para ausencias en exportaciones. Los porcentajes son números 0–100, no fracciones 0–1.

Cada petición lee el estado disponible al ejecutarse. Las páginas o paneles consultados por separado pueden cambiar si se registran operaciones entre peticiones; no se garantiza una foto transaccional conjunta. Exportar requiere recorrer todas las páginas con los mismos filtros. No usar `total` de una página como resumen de las fallas visibles de la cronología.

## Filtros generales

| Query | Tipo | Regla |
|---|---|---|
| `bus_id` | entero positivo | Alternativa a `n_bus`. |
| `n_bus` | texto, máximo 50 | Número normalizado, coincidencia exacta. |
| `solicitud_id` | entero positivo | OT exacta. |
| `estados` | repetible | REPORTADO, PENDIENTE, EN_REPARACION, LIBERADO, FINALIZADO. |
| `mecanicos_ids` | enteros positivos repetibles | Participación en OT, asignación, resolución o autoría de evento. |
| `meses` | enteros 1–12 repetibles | Mes de creación de OT en Santiago. |
| `anios` | enteros 1–9999 repetibles | Año de creación de OT en Santiago. |

Omitir significa Todos; no enviar `all`, listas JSON ni valores separados por comas. OR dentro de dimensión y AND entre dimensiones. No enviar `bus_id` y `n_bus` simultáneamente. El número de bus elimina espacios exteriores, prefijo `#` y ceros iniciales. Si una OT carece de FK, solo se vincula al maestro cuando su número normalizado tiene una coincidencia única. Una OT no vinculable se conserva en totales y tabla, pero no se atribuye a una ficha o estado actual ficticio.

```http
GET /api/v1/dashboard/indicadores?meses=9&meses=10&anios=2026&estados=PENDIENTE&estados=EN_REPARACION
```

Los payloads de query son DTOs con parámetros adicionales prohibidos. Bus/OT globales son exactos; las sugerencias son por prefijo. La OT local de tabla admite coincidencia parcial.

## Matriz de controles, cálculos y fuentes

| Control activo del prototipo | Endpoint | Cálculo / fuente |
|---|---|---|
| `statusKpis` | `/indicadores` | Solicitudes, último evento de OT, maestro activo de buses. |
| `timeKpis` | `/indicadores` | Primera asignación OT/falla, fechas estructuradas de término, detalles, reincidencias. |
| `statusPie`, leyenda | `/series/talleres` | Última ubicación por OT → evento → detalle → solicitud. |
| Tooltip Externos | `/talleres/externos` | Agrupación por nombre y ciudad snapshot. |
| `trendChart` | `/series/tendencia` | Creación y término por semana de lunes. |
| `agingChart` | `/series/antiguedad` | Última OT abierta por bus activo al final del día de referencia. |
| `mechanicChart` | `/series/mecanicos` | Fallas únicas por rol MECANICO. |
| `busFaultChart` | `/series/buses-fallas` | Conteo de detalles por bus. |
| `busVisitChart` | `/series/buses-visitas` | Conteo de estadías válidas por bus. |
| `machineKpis` | `/buses/{id}/resumen` | Estado, visitas, fallas, reincidencias del bus en el conjunto general filtrado. |
| Tooltip de estados de falla | `/buses/{id}/fallas` y `/fallas/solicitudes` | Descripción agrupada y OT distintas relacionadas. |
| Tarjetas visitas/reincidencias | `/solicitudes` con selección | Recalcula las OT relacionadas en servidor. |
| `machineTimelineList` | `/buses/{id}/cronologia` | Eventos de estado y hitos derivados de fechas estructuradas. |
| Tooltip por etapa | `/buses/{id}/cronologia/detalles?hito_id=...` | Último evento de falla hasta el hito y autores snapshot de ese evento. |
| Exportación cronología | `/cronologia/resumen` y `/cronologia/detalles` | Resumen SQL de todas las etapas seleccionadas y filas paginadas. |
| `ordersTable`, exportación tabla | `/solicitudes` | Misma población y mismos filtros para pantalla/PDF/Excel. |
| Autocompletados/selecciones | `/filtros/{recurso}` | Maestro, participación y períodos según contexto. |

No existe endpoint de exportación binaria ni endpoint para refrescar: se vuelven a consultar los recursos. La plantilla de archivos, colores, SVG, listeners y aislamiento CSS pertenecen al repositorio frontend.

## Cómo interpretar el payload

Todos los endpoints usan **GET sin body**. El bloque `payload` de cada ejemplo es una representación para el cliente: `path` sustituye variables de la ruta y `query` se serializa en la URL. No enviar ese objeto como JSON en el cuerpo. Adjuntar `Authorization: Bearer <access_token>` a cada petición. Para leer respuestas JSON puede enviarse `Accept: application/json`.

Las listas del payload se convierten en parámetros repetidos, por ejemplo `meses: [9, 10]` → `?meses=9&meses=10`. Enviar solo los filtros admitidos por el recurso; reiniciar `skip=0` cuando cambien. `bus_id` de ruta es obligatorio y positivo en los endpoints de buses.

Las seis series aceptan filtros generales, `periodos` (lista `YYYY-MM`), `skip` y `limit`. Los períodos se suman a los filtros generales; antigüedad conserva la excepción documentada en su sección. Las cuatro opciones de filtros aceptan filtros generales, `q`, `contexto`, `skip` y `limit`.

## Índice de rutas

Todas llevan el prefijo `/api/v1/dashboard`.

| Método | Ruta | Query adicional a filtros generales |
|---|---|---|
| GET | `/indicadores` | Ninguna; no admite paginación. |
| GET | `/series/{serie}` | `periodos`, `skip`, `limit`. |
| GET | `/talleres/externos` | `periodos`, `skip`, `limit`. |
| GET | `/solicitudes` | Períodos, filtros locales, selección, `skip`, `limit`. |
| GET | `/buses/{bus_id}/resumen` | Ninguna; no admite paginación. |
| GET | `/buses/{bus_id}/fallas` | `estado_falla` obligatorio, `skip`, `limit`. |
| GET | `/buses/{bus_id}/fallas/solicitudes` | `estado_falla` y `descripcion` obligatorios, `skip`, `limit`. |
| GET | `/buses/{bus_id}/cronologia` | `hito_meses`, `hito_anios`, `skip`, `limit`. |
| GET | `/buses/{bus_id}/cronologia/detalles` | Filtros de hitos, `hito_id` opcional, `skip`, `limit`. |
| GET | `/buses/{bus_id}/cronologia/resumen` | Filtros de hitos; la paginación no recorta el resumen. |
| GET | `/filtros/{recurso}` | `q`, `contexto`, `skip`, `limit`. |

`serie`: `tendencia`, `antiguedad`, `mecanicos`, `buses-fallas`, `buses-visitas`, `talleres`. `recurso`: `buses`, `solicitudes`, `mecanicos`, `periodos`.

## Endpoints, payloads y respuestas

### 1. Indicadores

```http
GET /api/v1/dashboard/indicadores?meses=10&anios=2026
Authorization: Bearer <access_token>
```

Acepta filtros generales, sin paginación. Total y finalizadas cuentan OT históricas; pendientes/en reparación/liberadas cuentan buses activos con su última OT. Las tarjetas mensuales usan el último mes de creación del conjunto filtrado. REPORTADO se conserva en el contrato sin exigir una tarjeta nueva.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "meses": [
      10
    ],
    "anios": [
      2026
    ]
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "estados": {
      "total_ot": 12,
      "pendientes_buses": 2,
      "en_reparacion_buses": 1,
      "liberados_buses": 1,
      "finalizadas_ot": 6,
      "reportadas_ot": 0
    },
    "tiempos": {
      "respuesta": {
        "promedio_horas": 2.5,
        "mediana_horas": 2,
        "validos": 8,
        "sin_datos": 3,
        "invalidos": 1
      },
      "reparacion": {
        "promedio_horas": 12,
        "mediana_horas": 10,
        "validos": 5,
        "sin_datos": 6,
        "invalidos": 1
      },
      "completo": {
        "promedio_horas": 14,
        "mediana_horas": 12,
        "validos": 6,
        "sin_datos": 6,
        "invalidos": 0
      }
    },
    "mensuales": {
      "periodo": "2026-10",
      "ot_atendidas": 8,
      "ot_totales": 12,
      "porcentaje_ot_atendidas": 66.67,
      "fallas_atendidas": 20,
      "fallas_reportadas": 30,
      "porcentaje_fallas_atendidas": 66.67,
      "reincidencias": 3
    }
  }
}
```

### 2. Tendencia semanal

```http
GET /api/v1/dashboard/series/tendencia?periodos=2026-10&skip=0&limit=20
Authorization: Bearer <access_token>
```

La semana empieza el lunes. Terminadas requiere término y estado LIBERADO o FINALIZADO. Los períodos seleccionan creación de OT; el término puede ocurrir después. No existe parámetro para cambiar la agrupación a día o mes.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "periodos": [
      "2026-10"
    ],
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "semana": "2026-10-19",
        "creadas": 8,
        "terminadas": 5
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20,
    "serie": "tendencia",
    "periodos_aplicados": [
      "2026-10"
    ]
  }
}
```

### 3. Antigüedad de OT abiertas

```http
GET /api/v1/dashboard/series/antiguedad?periodos=2026-10&skip=0&limit=20
Authorization: Bearer <access_token>
```

Solo última OT abierta por bus activo, sin término y pendiente/en reparación. Ignora meses/años generales; conserva los demás filtros y períodos propios. Compara con el final del último día de creación disponible, no necesariamente con hoy. Los grupos pueden tener cero.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "periodos": [
      "2026-10"
    ],
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "grupo": "HASTA_7_DIAS",
        "cantidad": 4
      },
      {
        "grupo": "MAS_7_HASTA_28_DIAS",
        "cantidad": 2
      },
      {
        "grupo": "MAS_28_DIAS",
        "cantidad": 1
      }
    ],
    "total": 3,
    "skip": 0,
    "limit": 20,
    "serie": "antiguedad",
    "periodos_aplicados": [
      "2026-10"
    ],
    "fecha_corte_calculo": "2026-10-27T02:59:59.999999Z"
  }
}
```

### 4. Participación de mecánicos

```http
GET /api/v1/dashboard/series/mecanicos?periodos=2026-10&skip=0&limit=20
Authorization: Bearer <access_token>
```

Personas con rol MECANICO, incluyendo perfiles inactivos para historia. Cuenta fallas únicas por persona integrando asignaciones de OT/falla, resolutor y autores de eventos. Puede incluir personas con cero fallas.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "periodos": [
      "2026-10"
    ],
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "mecanico_id": 9005,
        "nombre_completo": "Mecánico de ejemplo",
        "fallas_unicas": 14
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20,
    "serie": "mecanicos",
    "periodos_aplicados": [
      "2026-10"
    ]
  }
}
```

### 5. Top 5 por fallas

```http
GET /api/v1/dashboard/series/buses-fallas?periodos=2026-10&skip=0&limit=20
Authorization: Bearer <access_token>
```

Cuenta detalles de falla de las OT filtradas. Máximo cinco buses identificados, por cantidad descendente y bus ID como desempate.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "periodos": [
      "2026-10"
    ],
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "bus_id": 9004,
        "n_bus": "354",
        "cantidad": 12
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20,
    "serie": "buses-fallas",
    "periodos_aplicados": [
      "2026-10"
    ]
  }
}
```

### 6. Top 5 por visitas

```http
GET /api/v1/dashboard/series/buses-visitas?periodos=2026-10&skip=0&limit=20
Authorization: Bearer <access_token>
```

Cuenta estadías válidas de las OT filtradas. Máximo cinco buses; no reconstruye visitas desde correcciones ni consolidaciones.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "periodos": [
      "2026-10"
    ],
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "bus_id": 9004,
        "n_bus": "354",
        "cantidad": 3
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20,
    "serie": "buses-visitas",
    "periodos_aplicados": [
      "2026-10"
    ]
  }
}
```

### 7. OT por taller responsable

```http
GET /api/v1/dashboard/series/talleres?periodos=2026-10&skip=0&limit=20
Authorization: Bearer <access_token>
```

Una OT cuenta una vez según la última ubicación registrada, con desempate por ID. Usa tipo/ciudad/nombre snapshot. El denominador es ot_clasificadas; ausencias y ubicaciones no clasificables no se atribuyen a un taller.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "periodos": [
      "2026-10"
    ],
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "grupo": "INTERNO_TEMUCO",
        "cantidad": 8,
        "porcentaje": 80
      },
      {
        "grupo": "INTERNO_SANTIAGO",
        "cantidad": 0,
        "porcentaje": 0
      },
      {
        "grupo": "EXTERNOS",
        "cantidad": 2,
        "porcentaje": 20
      }
    ],
    "total": 3,
    "skip": 0,
    "limit": 20,
    "serie": "talleres",
    "periodos_aplicados": [
      "2026-10"
    ],
    "ot_clasificadas": 10,
    "ot_sin_ubicacion": 4,
    "ot_no_clasificables": 1
  }
}
```

### 8. Desglose de talleres externos

```http
GET /api/v1/dashboard/talleres/externos?periodos=2026-10&skip=0&limit=20
Authorization: Bearer <access_token>
```

Mismos filtros y períodos que talleres. Agrupa nombre y ciudad históricos. El porcentaje se calcula sobre OT externas, no sobre todas las OT.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "periodos": [
      "2026-10"
    ],
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "nombre_snapshot": "Taller de ejemplo",
        "ciudad_snapshot": "Temuco",
        "ot": 2,
        "porcentaje_del_total_externo": 100
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20
  }
}
```

### 9. Tabla y datos de exportación de OT

```http
GET /api/v1/dashboard/solicitudes?seleccion_tipo=taller&seleccion_grupo=EXTERNOS&seleccion_periodos=2026-10&tabla_estados=FINALIZADO&skip=0&limit=20
Authorization: Bearer <access_token>
```

Acepta filtros generales, periodos, filtros locales de tabla y selección desde gráficos. Ordena creación e ID descendentes. PDF/Excel usan todas las páginas del mismo resultado; no hay endpoint de exportación binaria.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "seleccion_tipo": "taller",
    "seleccion_grupo": "EXTERNOS",
    "seleccion_periodos": [
      "2026-10"
    ],
    "tabla_estados": [
      "FINALIZADO"
    ],
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "id": 9001,
        "bus_id": 9004,
        "n_bus": "354",
        "estado": "FINALIZADO",
        "total_fallas": 3,
        "fecha_creacion": "2026-10-20T12:00:00Z",
        "fecha_termino": "2026-10-21T18:00:00Z",
        "completo_horas": 30
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20
  }
}
```

### 10. Resumen del bus

```http
GET /api/v1/dashboard/buses/9004/resumen?meses=10&anios=2026
Authorization: Bearer <access_token>
```

Acepta filtros generales sin paginación. El bus de la ruta y los filtros se intersectan. La ficha sí recibe filtros generales, como el código real. FINALIZADO se presenta como En servicio en el cliente; sin OT el estado y ultima_ot_id son null.

**Payload (ruta y query; sin body):**

```json
{
  "path": {
    "bus_id": 9004
  },
  "query": {
    "meses": [
      10
    ],
    "anios": [
      2026
    ]
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "bus": {
      "id": 9004,
      "n_bus": "354",
      "patente": "EJEMPLO"
    },
    "ultima_ot_id": 9001,
    "estado": "FINALIZADO",
    "visitas": 5,
    "fallas": {
      "pendientes": 1,
      "incompletas": 0,
      "resueltas": 12
    },
    "reincidencias": {
      "periodo": "2026-10",
      "cantidad": 2
    }
  }
}
```

### 11. Fallas agrupadas del bus

```http
GET /api/v1/dashboard/buses/9004/fallas?estado_falla=PENDIENTE&skip=0&limit=20
Authorization: Bearer <access_token>
```

estado_falla es obligatorio: PENDIENTE, INCOMPLETA o RESUELTA. Admite filtros generales y paginación. Agrupa por descripción original, con alternativa snapshot y etiqueta si falta descripción.

**Payload (ruta y query; sin body):**

```json
{
  "path": {
    "bus_id": 9004
  },
  "query": {
    "estado_falla": "PENDIENTE",
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "descripcion": "Falla de ejemplo",
        "cantidad": 2
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20
  }
}
```

### 12. OT relacionadas con una falla agrupada

```http
GET /api/v1/dashboard/buses/9004/fallas/solicitudes?estado_falla=PENDIENTE&descripcion=Falla%20de%20ejemplo&skip=0&limit=20
Authorization: Bearer <access_token>
```

estado_falla y descripcion exacta son obligatorios. Devuelve OT distintas, por ID descendente. Admite los mismos filtros generales y evita arrays anidados ilimitados.

**Payload (ruta y query; sin body):**

```json
{
  "path": {
    "bus_id": 9004
  },
  "query": {
    "estado_falla": "PENDIENTE",
    "descripcion": "Falla de ejemplo",
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "solicitud_id": 9010
      },
      {
        "solicitud_id": 9011
      }
    ],
    "total": 2,
    "skip": 0,
    "limit": 20
  }
}
```

### 13. Cronología del bus

```http
GET /api/v1/dashboard/buses/9004/cronologia?meses=10&anios=2026&hito_meses=10&hito_anios=2026&skip=0&limit=20
Authorization: Bearer <access_token>
```

meses/anios filtra creación de OT; hito_meses/hito_anios filtra fecha del hito. Se aplican conjuntamente. Prioriza eventos, completa hitos ausentes con fechas estructuradas y marca derivado=true. Orden por fecha descendente y desempates estables.

**Payload (ruta y query; sin body):**

```json
{
  "path": {
    "bus_id": 9004
  },
  "query": {
    "meses": [
      10
    ],
    "anios": [
      2026
    ],
    "hito_meses": [
      10
    ],
    "hito_anios": [
      2026
    ],
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "hito_id": "evento:9003",
        "solicitud_id": 9001,
        "tipo_evento": "CREACION",
        "fecha_evento": "2026-10-20T12:00:00Z",
        "estado_anterior": null,
        "estado_nuevo": "PENDIENTE",
        "derivado": false,
        "creador_nombre": "Creador de ejemplo"
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20
  }
}
```

### 14. Detalle de una etapa y filas del informe

```http
GET /api/v1/dashboard/buses/9004/cronologia/detalles?hito_id=evento%3A9003&skip=0&limit=20
Authorization: Bearer <access_token>
```

Mismos filtros que cronología. hito_id es opcional: con él consulta una etapa; sin él devuelve todas las filas del informe paginadas. Debe pertenecer al bus y filtros. Estado y autores corresponden al evento histórico hasta esa fecha; no se copia el resolutor actual. Etapas sin fallas conservan una fila con detalle_id y campos de falla null.

**Payload (ruta y query; sin body):**

```json
{
  "path": {
    "bus_id": 9004
  },
  "query": {
    "hito_id": "evento:9003",
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "solicitud_id": 9001,
        "hito_id": "evento:9003",
        "tipo_evento": "CREACION",
        "fecha_evento": "2026-10-20T12:00:00Z",
        "estado_ot": "PENDIENTE",
        "creador_nombre": "Creador de ejemplo",
        "detalle_id": 9002,
        "descripcion": "Falla de ejemplo",
        "fecha_reporte": "2026-10-20T12:00:00Z",
        "reportante_nombre": null,
        "estado_falla": "PENDIENTE",
        "mecanicos_nombres": []
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20
  }
}
```

### 15. Resumen del informe de cronología

```http
GET /api/v1/dashboard/buses/9004/cronologia/resumen?hito_meses=10&hito_anios=2026
Authorization: Bearer <access_token>
```

Acepta filtros generales y de hitos. Aunque admite skip/limit heredados del DTO, estos no recortan los conteos. Cada falla se clasifica por su último estado visible en las etapas seleccionadas. estado_actual procede del historial completo del bus, sin filtros; por eso puede diferir del estado de la ficha filtrada.

**Payload (ruta y query; sin body):**

```json
{
  "path": {
    "bus_id": 9004
  },
  "query": {
    "hito_meses": [
      10
    ],
    "hito_anios": [
      2026
    ]
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "bus": {
      "id": 9004,
      "n_bus": "354",
      "patente": "EJEMPLO"
    },
    "estado_actual": "FINALIZADO",
    "ot_distintas": 4,
    "fallas_distintas": 10,
    "resueltas": 6,
    "pendientes": 2,
    "incompletas": 1,
    "sin_estado_documentado": 1
  }
}
```

### 16. Buses disponibles

```http
GET /api/v1/dashboard/filtros/buses?contexto=maquina&q=35&skip=0&limit=20
Authorization: Bearer <access_token>
```

contexto=general|maquina|tabla. General/tabla considera otros filtros y omite el bus de la propia sugerencia. Máquina ofrece el maestro activo, incluso buses sin OT. q busca prefijo normalizado.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "contexto": "maquina",
    "q": "35",
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "bus_id": 9004,
        "n_bus": "354",
        "patente": "EJEMPLO"
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20
  }
}
```

### 17. OT disponibles

```http
GET /api/v1/dashboard/filtros/solicitudes?q=90&skip=0&limit=20
Authorization: Bearer <access_token>
```

contexto=general|tabla. Considera los demás filtros y omite solicitud_id para la sugerencia. q busca prefijo del ID.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "q": "90",
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "id": 9001,
        "n_bus": "354"
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20
  }
}
```

### 18. Mecánicos disponibles

```http
GET /api/v1/dashboard/filtros/mecanicos?q=ejemplo&skip=0&limit=20
Authorization: Bearer <access_token>
```

contexto=general. Ofrece rol MECANICO incluyendo perfiles inactivos para historia. q busca texto por nombre; no devuelve username ni teléfono.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "q": "ejemplo",
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "id": 9005,
        "nombre_completo": "Mecánico de ejemplo",
        "is_active": true
      },
      {
        "id": 9006,
        "nombre_completo": "Mecánico histórico de ejemplo",
        "is_active": false
      }
    ],
    "total": 2,
    "skip": 0,
    "limit": 20
  }
}
```

### 19. Períodos disponibles

```http
GET /api/v1/dashboard/filtros/periodos?contexto=cronologia&bus_id=9004&skip=0&limit=20
Authorization: Bearer <access_token>
```

contexto=ot|cronologia. OT usa creación; cronología incorpora hitos registrados/derivados y admite bus_id. Orden descendente; el primer período identifica el último disponible. No se usa q para períodos.

**Payload (ruta y query; sin body):**

```json
{
  "path": {},
  "query": {
    "contexto": "cronologia",
    "bus_id": 9004,
    "skip": 0,
    "limit": 20
  }
}
```

**Respuesta 200:**

```json
{
  "metadata": {
    "version_contrato": 1,
    "generado_en": "2026-10-27T16:30:00Z",
    "zona_horaria": "America/Santiago",
    "fecha_referencia_datos": "2026-10-26"
  },
  "data": {
    "items": [
      {
        "periodo": "2026-10",
        "mes": 10,
        "anio": 2026
      }
    ],
    "total": 1,
    "skip": 0,
    "limit": 20
  }
}
```

## Reglas para conectar controles y leer métricas

### Filtros propios de la tabla y selección de gráficos

Filtros generales y estos filtros locales adicionales:

| Query | Regla |
|---|---|
| `tabla_n_bus` | Número exacto normalizado. |
| `tabla_ot` | Subcadena del número de OT, con prefijo # opcional. |
| `tabla_estados` | Estados repetibles. |
| `tabla_periodos` | Períodos YYYY-MM repetibles. |
| `tabla_anios` | Años repetibles. |

No sustituyen filtros generales. Filtros incompatibles producen conjunto vacío.

| `seleccion_tipo` | Query requerido |
|---|---|
| `taller` | `seleccion_grupo=INTERNO_TEMUCO|INTERNO_SANTIAGO|EXTERNOS` |
| `antiguedad` | `seleccion_grupo=HASTA_7_DIAS|MAS_7_HASTA_28_DIAS|MAS_28_DIAS` |
| `mecanico` | `seleccion_mecanico_id` |
| `bus_fallas`, `bus_visitas`, `visitas_bus` | `seleccion_bus_id` |
| `creadas`, `terminadas` | `seleccion_semana=YYYY-MM-DD` (lunes) |
| `reincidencias_bus` | `seleccion_bus_id`, `seleccion_periodo=YYYY-MM` |

`seleccion_periodos` conserva los períodos del gráfico de origen. No enviar parámetros de otro tipo de selección ni listas calculadas de OT. Antigüedad conserva la población del gráfico, ignorando los meses/años generales; los filtros locales de tabla siguen aplicando. Las tarjetas de estado modifican el filtro general de estado y no requieren un tipo de selección especial.


Orden de OT: creación descendente e ID descendente. `visitas_bus` exige visitas; `bus_visitas` selecciona las OT del bus en el período del ranking. Reincidencias incluye OT posteriores y antecedentes, intersectados con los filtros solicitados. Seleccionar un gráfico solo cambia la tabla.

### Indicadores y ausencias

- Total/finalizadas cuentan OT históricas filtradas; reportadas conserva cobertura de REPORTADO sin inventar una tarjeta nueva.
- Pendientes/en reparación/liberadas cuentan buses activos con su última OT. Para elegirla se ignoran estado y mes/año generales, se mantienen bus/OT/mecánico, y se aplica estado después. No sumar estas tarjetas para inferir el total histórico.
- Estado efectivo: último evento con estado informado, por fecha e ID; si falta, estado de la OT.
- Respuesta = primera asignación de mecánico − creación. Reparación = término − primera asignación. Completo = término − creación.
- Término = menor fecha entre liberación y cierre; no se leen comentarios para deducirlo. Las duraciones negativas no se convierten a cero; se excluyen con su contador de inválidos. Los problemas de fechas de falla no invalidan un intervalo de OT que usa otras fechas.
- Mes mensual = último mes de creación de OT del conjunto filtrado. OT atendidas = EN_REPARACION/LIBERADO/FINALIZADO. Fallas atendidas = RESUELTA/INCOMPLETA; ambas clases permanecen distintas.
- Sin observaciones: conteos cero, período/porcentajes/promedios/medianas null.


### Reincidencias y reconstrucción histórica

Reincidencias del bus usa el último mes global de creación disponible. Coincide bus + descripción normalizada (minúscula, ASCII NFKD, sin puntuación y espacios compactos) en un intervalo de 0 a 30 días inclusivos, por fecha de reporte o creación del detalle. Antecedentes pueden estar fuera del período filtrado; la falla posterior debe pertenecer a las OT seleccionadas. Los buses sin asociación única no se mezclan entre sí.

Una falla se incluye si su reporte o un evento documentado ya existía al hito. Estado = último evento con estado informado hasta esa fecha, por fecha e ID. En creación, un reporte ya existente sin evento se presenta pendiente; en otras etapas, un estado no reconstruible queda null. No usar el resolutor actual como sustituto de autoría histórica. Nombres del evento proceden de sus snapshots; solo se muestran en RESUELTA/INCOMPLETA.

Las etapas sin fallas conservan fila con detalle/descripcion/fecha de reporte/estado nulos y mecánicos vacíos. La autoría se consulta en bloque para los eventos de la página, no una petición SQL por etapa.


Los identificadores derivados tienen formato `derivado:<ot>:CREACION|EN_REPARACION|LIBERADO|FINALIZADO`. Usar siempre el `hito_id` devuelto por el servidor, sin construirlo desde la posición de una fila. Para consultar todos los detalles del informe, omitir `hito_id` y mantener los mismos filtros de cronología.

## Ejemplo de consumo desde frontend

Ejemplo JavaScript reutilizable. `origin` es el origen configurado del backend, por ejemplo el de desarrollo autorizado; `token` procede del login existente. `filters` representa solo query. No agrega `Content-Type` porque el GET no tiene cuerpo.

```javascript
export async function dashboardGet(origin, resource, filters, token, signal) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters ?? {})) {
    const values = Array.isArray(value) ? value : [value];
    for (const item of values) {
      if (item !== undefined && item !== null && item !== "") {
        query.append(key, String(item));
      }
    }
  }

  const url = new URL(
    "/api/v1/dashboard/" + resource.replace(/^\/+/, ""),
    origin
  );
  url.search = query.toString();
  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: "Bearer " + token,
      Accept: "application/json"
    },
    cache: "no-store",
    signal
  });
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error?.message ?? "Error al consultar dashboard");
    error.status = response.status;
    error.code = payload.error?.code;
    error.detail = payload.error?.detail;
    throw error;
  }
  return payload; // { metadata, data }
}

const result = await dashboardGet(
  apiOrigin,
  "indicadores",
  { meses: [9, 10], anios: [2026], estados: ["PENDIENTE", "EN_REPARACION"] },
  accessToken,
  abortController.signal
);
const { metadata, data } = result;
```

Crear un `AbortController` por carga y cancelar la carga anterior al cambiar filtros o desmontar la vista. Si la biblioteca de consultas ya controla cancelaciones y claves por filtros, usar ese mecanismo. Un `AbortError` por cancelación no se presenta como fallo del servidor. En frontend y backend con orígenes distintos, el origen del cliente debe estar autorizado por la configuración CORS existente.

### Recorrer páginas para exportar

Enviar los mismos filtros y selección en todas las páginas, aumentando `skip` por la cantidad recibida. Solicitar como máximo 100 filas por petición. Usar `/solicitudes` para la tabla y `/buses/{bus_id}/cronologia/detalles` sin `hito_id` para el informe completo; acompañar este último con `/cronologia/resumen`, manteniendo sus filtros generales y de hitos.

```javascript
export async function dashboardAllPages(origin, resource, filters, token, signal) {
  const rows = [];
  let skip = 0;
  while (true) {
    const { data } = await dashboardGet(
      origin, resource, { ...filters, skip, limit: 100 }, token, signal
    );
    rows.push(...data.items);
    skip += data.items.length;
    if (data.items.length === 0 || skip >= data.total) break;
  }
  return rows;
}
```

El frontend genera PDF/XLSX con las filas reunidas. No calcular el resumen histórico sumando filas de detalles, porque una falla puede aparecer en varias etapas; utilizar `/cronologia/resumen`. Las operaciones confirmadas entre peticiones pueden cambiar el conjunto exportado; la API no mantiene un corte entre páginas.

## Valores iniciales y limpieza

- Globales: Todos.
- Talleres y mecánicos: último período de creación al cargar.
- Tendencia, antigüedad y rankings: Todos.
- Cronología: mes/año de hitos en Todos y cerrada inicialmente (estado visual).
- Limpiar general: talleres vuelve al último período, mecánicos y demás gráficos quedan en Todos.
- Limpiar tabla no cambia gráficos/globales. Limpiar cronología solo quita filtros de hitos.
- Actualizar no reinicia estos estados: vuelve a pedir sus datos conservando filtros.

## Errores, privacidad y diferencias respecto del prototipo

```json
{"error":{"code":"FORBIDDEN","message":"Acceso denegado: Se requieren permisos de SUPERVISOR o ADMIN.","detail":null}}
```

401 sesión inválida/expirada; 403 rol; 404 bus/hito inexistente o ajeno a los filtros; 422 validación/selección incompatible; 500 fallo interno sin SQL ni secretos. Vacío válido = 200. El módulo no devuelve username, teléfono, hash, credenciales, bitácoras ni evidencias.

| Prototipo | Módulo integrado |
|---|---|
| Cuatro JSON y simulación mezclados | Lecturas de la conexión operacional existente, bajo demanda. |
| IDs fijos de mecánicos | Rol MECANICO y participación histórica. |
| Asignación OT omitida por falta de detalle_id | Su participación incluye los detalles de esa OT. |
| Término también inferido desde comentarios | Solo liberación/cierre, según decisión acordada. |
| Intervalos negativos convertidos a cero | Null y contador de inválidos. |
| Dos implementaciones de reincidencia con fechas diferentes | Fecha de reporte/creación y antecedentes previos al período. |
| Arrays completos en memoria | Agregaciones SQL y páginas acotadas. |
| Supuesto de estado En servicio sin OT | Estado null; no inferir disponibilidad. |
| Posible resolutor actual en una etapa antigua | Autoría del evento histórico documentado. |
| Documentación que describe ficha independiente | Se conserva el código ejecutado: ficha/cronología reciben filtros generales. |

No se incorpora `renderHighlights`, selección de métricas sin control activo, gráfica independiente de reincidencias, tareas diarias, almacenamiento de resultados ni exportación binaria en backend. El frontend todavía debe sustituir su capa de datos; registrar la API no conecta por sí solo la página estática.


## Manejo de errores en el cliente

Los errores usan `error`, sin el envoltorio `metadata/data`. Conservar el HTTP status y `error.code`; mostrar `error.message` y, para validación, asociar `detail` a los campos. No reutilizar una pantalla vacía para presentar una consulta que falló.

Los errores de validación incluyen `detail` como lista de objetos con `field` (ruta del campo) y `msg` (descripción). Las excepciones HTTP de FastAPI/Starlette pueden usar `HTTP_ERROR`; manejar también el status, sin depender únicamente del código de dominio.

| HTTP | Código | Acción del cliente |
|---|---|---|
| 401 | `UNAUTHORIZED` | Gestionar sesión mediante el flujo de autenticación existente. |
| 403 | `FORBIDDEN` | Mostrar acceso denegado. |
| 404 | `NOT_FOUND` | Bus/hito inexistente o hito fuera del bus/filtros solicitados. |
| 422 | `VALIDATION_ERROR` | Revisar tipos, campos y límites. |
| 422 | `BUSINESS_RULE_VIOLATION` | Corregir combinación de filtros o selección. |
| 500 | `INTERNAL_ERROR` | Informar fallo y permitir reintento manual. |

Ejemplo de combinación inválida (422):

```json
{
  "error": {
    "code": "BUSINESS_RULE_VIOLATION",
    "message": "Use bus_id o n_bus, no ambos.",
    "detail": null
  }
}
```

Si un middleware rechaza el origen antes de ejecutar la ruta, su respuesta puede no tener este envoltorio; comprobar la configuración de origen autorizada. Un vacío válido devuelve 200: `items=[]` y `total=0`; las series de grupos fijos pueden mantener filas con cantidad cero. No reemplazar `null` por `0` mediante `valor || 0`.

## Verificación y referencia de implementación

Las solicitudes y respuestas ilustrativas de las 19 variantes de este documento se validan contra los DTOs implementados. Las 19 variantes cubren once rutas: seis series comparten una ruta y cuatro catálogos comparten otra. La validación documental no consulta la base de datos ni sustituye una prueba de integración del frontend.

Fuentes: `app/modules/dashboard/api/router.py`, `app/modules/dashboard/dtos/` y servicios/repositorios del módulo. OpenAPI publica los modelos de entrada y respuesta. Para integrar, comprobar autorización, arrays repetidos, cambio de filtros, paginación, cancelación de cargas, valores nulos y la igualdad entre selección del gráfico y tabla. Actualizar repite las consultas visibles manteniendo filtros.
