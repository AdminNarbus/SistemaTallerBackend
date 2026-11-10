# Revisión individual de fallas

Cada detalle expone `estado_revision` (`PENDIENTE` o `APROBADA`),
`revisado_por_id` y `fecha_revision`. Esta revisión es independiente de
`estado` (`PENDIENTE`, `INCOMPLETA`, `RESUELTA`) y de `es_ot`.

## Reglas

- Un reporte de conductor queda pendiente, incluso si el bus ya tiene una OT aceptada.
- Un mecánico que reporta sin autoasignarse y sin asignaciones activas previas en esa OT deja la falla pendiente.
- Si el mecánico ya tiene alguna falla asignada activamente en la misma OT, sus nuevas fallas se aprueban automáticamente.
- Agregar una falla con `autoasignar=true` aprueba esa falla y la asigna al mecánico.
- Al autoasignarse fallas existentes, se aprueban únicamente las seleccionadas. Las demás conservan su revisión.
- La asignación por supervisión aprueba las fallas seleccionadas. Las fallas reportadas por supervisión se consideran aprobadas.
- Aprobar inicialmente una solicitud como OT, incluida su primera toma de trabajo, aprueba sus fallas actuales. Si la conversión ocurre por asignación o autoasignación de fallas específicas, se aprueban únicamente las seleccionadas. Repetir la aprobación de una cabecera que ya es OT no aprueba reportes posteriores.
- Una falla pendiente de revisión puede conservarse en `detalles` para su revisión, pero no permite registrar resultados, check de reparación, falta de repuestos ni consumo de repuestos.
- Los contadores existentes siguen contando reportes; el frontend debe usar `estado_revision` para distinguir las fallas autorizadas de las pendientes de revisión.

## Visto bueno sin asignación

`PATCH /api/v1/supervision/solicitudes/{id}/detalles/{detalle_id}/aprobar`

Sin cuerpo. Requiere supervisor o administrador; la OT debe estar aceptada y abierta
(incluye `LIBERADO`). Devuelve `SolicitudDTO` con la revisión actualizada,
registra un comentario de supervisión y emite el evento de actualización.
La repetición es idempotente y conserva el primer autor y fecha.

## Migración

`041_revision_fallas`, posterior a `040_rol_visual`, agrega las tres columnas,
la FK a usuarios, un CHECK de estados y los índices. Las fallas existentes de
OT aceptadas quedan `APROBADA`; las de solicitudes sin aceptar quedan
`PENDIENTE`. No se inventan aprobadores ni fechas históricos.

La migración está preparada; no se aplicó a bases externas durante este cambio.
