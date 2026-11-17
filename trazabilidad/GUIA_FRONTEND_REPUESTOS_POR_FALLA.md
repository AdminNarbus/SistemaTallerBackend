# API de repuestos utilizados por falla

El catálogo empieza vacío. Supervisión y administración incorporan artículos mediante la API; no hay importación de Excel ni control de stock.

## Catálogo

Prefijo `/api/v1/taller`. `GET /repuestos?q=valvula&skip=0&limit=20` busca por código, nombre o parte. Por defecto devuelve activos; supervisión y administración pueden solicitar `incluir_inactivos=true`. El total se entrega en `X-Total-Count` y el límite máximo es 100. Mecánicos, supervisores y administradores pueden consultar.

Supervisión o administración pueden crear con `POST /repuestos`:

```json
{"codigo":"R-100", "nombre":"Válvula", "parte":"A123", "unidad":"UN", "precio":598, "iva":113.62, "clasificacion":"REPUESTOS", "clasificacion_1":"FRENOS", "modelo":"MB"}
```

`codigo` y `nombre` son obligatorios; los otros campos son opcionales. Precio es neto unitario e IVA es monto unitario informativo. `PATCH /repuestos/{repuesto_id}` permite editar el código y demás campos, y activar/desactivar con `is_active`. El ID es estable; un código duplicado devuelve 409.

## Usos por falla

`GET /{ot_id}/detalles/{detalle_id}/repuestos-utilizados` consulta la falla; `GET /{ot_id}/repuestos-utilizados` consulta toda la OT. Ambos aceptan `skip`, `limit` e `incluir_anulados=true`, y exponen `X-Total-Count`. El resultado incluye cantidad y datos históricos del artículo, actor y fecha. El bus se obtiene de la OT.

`POST /{ot_id}/detalles/{detalle_id}/repuestos-utilizados` registra un tipo de artículo:

```json
{"repuesto_id": 1, "cantidad": "2", "operacion_id": "30efaab2-1000-4000-8000-000000000001"}
```

Cantidad debe ser mayor que cero y admite decimales. La falla puede tener cero, uno o varios artículos. Un artículo solo puede tener un registro vigente por falla; para corregir la cantidad, anular y volver a registrar. Un 201 indica alta; 200, repetición sin alta.

`PATCH /{ot_id}/detalles/{detalle_id}/repuestos-utilizados/{registro_id}/anulacion` recibe:

```json
{"motivo":"Selección incorrecta", "operacion_id":"30efaab2-1000-4000-8000-000000000002"}
```

El cliente genera un UUID para cada acción y reutiliza el mismo UUID y payload solo para reintentar esa acción. El recibo de un reintento es histórico; consultar con GET para conocer el estado vigente. Una operación distinta con un UUID ya usado devuelve 409.

El mecánico requiere una asignación activa a la falla; supervisión y administración pueden registrar sin asignación. El mecánico solo puede anular sus propios registros; la OT debe estar aprobada y no finalizada. No es obligatorio registrar repuestos para resolver una falla.

Cada alta o anulación incorpora a la bitácora un mensaje con falla, código, nombre y cantidad. Una falla con registros de repuestos, incluidos anulados, no puede eliminarse. La cantidad no afecta existencias.


## Validación de revisión y fechas (2026-11-09)

La falla debe tener `estado_revision=APROBADA` antes de registrar o anular consumos. La autoasignación aprueba las fallas seleccionadas. Los IDs de ruta deben ser mayores que cero. Las fechas `created_at` y `fecha_anulacion` se entregan en UTC. Se contrasta el rol actual del autor con la sesión antes de las mutaciones y de devolver sus recibos. El rol VISUAL conserva la excepción global de lectura, incluidos los artículos inactivos; no puede crear, editar, registrar ni anular.

Revisión y evidencias: [Informe de repuestos](../docs/REVISION_REPUESTOS_20261109.md).
