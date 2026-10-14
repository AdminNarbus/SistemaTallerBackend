# Comentarios breves y asignación grupal de OT

Los nuevos comentarios automáticos omiten el nombre del autor, «marcado/registrado por» y los prefijos «Nota», «Motivo», «Observación» y «Comentario de cierre». El texto escrito se añade directamente, separado por un punto. `usuario_nombre`, `usuario_id`, `tipo`, `fecha_registro` y `fecha_evento` siguen disponibles para mostrar el indicador junto al autor y la hora.

Los nombres de destinatarios y resolutores se conservan cuando aportan información: una asignación hecha por supervisión, una reparación realizada por otro mecánico o por un equipo. Una reparación individual registrada por el propio mecánico omite su nombre del texto.

## Asignar varios mecánicos con una sola petición

Se acepta `mecanicos_ids` en las dos rutas existentes:

- `POST /api/v1/taller/{id}/asignar`
- `POST /api/v1/supervision/solicitudes/{id}/asignar`

```json
{
  "mecanicos_ids": [2, 3],
  "detalles_ids": [10, 20],
  "comentario": "Viendo en fosa"
}
```

El servicio valida el grupo antes de escribir, asigna cada falla a cada integrante y añade **un solo comentario después de ambos bucles**:

> Asignación: Ricardo y Cecil — Sin A/C, Freno largo. Viendo en fosa

Los IDs repetidos se deduplican y las asignaciones/presencias ya activas se reutilizan. Se conserva `mecanico_id` para clientes que envían un solo mecánico. Si hay lista no vacía y campo singular, se prioriza la lista. Un grupo vacío, un ID no positivo o un usuario inexistente/inactivo se rechaza.

**Integración del frontend:** la selección múltiple debe enviar una sola petición con `mecanicos_ids`. Si sigue haciendo una petición por mecánico, cada petición continúa siendo una acción independiente con su propio comentario. Este repositorio contiene el backend; aquí no se modificó ese bucle del frontend.

## Textos por acción

| Acción | Formato nuevo |
| --- | --- |
| Anexar reporte a una OT existente | `Reporte: 2 nueva(s) falla(s). Texto del reporte` |
| Tomar OT | `Inicio: Sin A/C` |
| Tomar OT con equipo | `Inicio: Sin A/C (Ricardo y Cecil). Viendo en fosa` |
| Autoasignar fallas | `Inicio: Sin A/C`, con participantes entre paréntesis si hay equipo |
| Asignación desde supervisión | `Asignación: Ricardo y Cecil — Sin A/C. Viendo en fosa` |
| Salir del equipo | `Salida. Texto escrito` |
| Entregar turno | `Entrega de turno. Texto escrito` |
| Terminar avance individual | `Avance: Sin A/C. Texto escrito` |
| Terminar avance grupal | `Avance: Ricardo y Cecil: Sin A/C. Texto escrito` |
| Agregar avería | `Nueva falla: Sin A/C` |
| Agregar avería asignada | `Nueva falla: Sin A/C. Asignación: Ricardo` |
| Reparación propia | `Reparó: Sin A/C. Texto escrito` |
| Reparación de otro mecánico o registrada por supervisión | `Ricardo reparó: Sin A/C. Texto escrito` |
| Reparación grupal | `Ricardo y Cecil repararon: Sin A/C. Texto escrito` |
| Falla incompleta | `Incompleta: Sin A/C. Motivo escrito. Comentario adicional` |
| Reapertura de falla | `Reapertura: Sin A/C. Texto escrito` |
| Falta de repuesto | `Falta repuesto: Sin A/C. Texto escrito` |
| Repuesto disponible | `Repuesto disponible: Sin A/C. Texto escrito` |
| Cierre liberando bus | `Cierre: bus liberado. Texto de cierre. Justificaciones` |
| Cierre dejando bus en taller | `Cierre: bus en taller. Texto de cierre. Justificaciones` |
| Cambio de estado de OT | `REPORTADO → EN REPARACION. Texto escrito` |
| Guardar pauta | `Pauta: 3 ítem(s)` |

Las partes opcionales se omiten cuando están vacías. En una falla incompleta no se repite el comentario si es igual al motivo. Se conservan íntegros los nombres almacenados de mecánicos y fallas; no se acortan apellidos ni se cambia el texto libre del usuario, salvo quitar espacios en sus extremos.

Los comentarios históricos ya almacenados conservan su texto. No se cambian los estados, fechas de eventos ni reglas de reparación/cierre por este ajuste. Los comentarios manuales mantienen el contenido recibido.

## Código

- `app/modules/taller/services/bitacora_textos.py`: composición de notas, nombres, reparación y transición de estado.
- `app/modules/taller/dtos/cuadrilla_dto.py`: entrada plural compatible con el campo singular.
- `app/modules/taller/services/cuadrilla_service.py`: asignación grupal y mensaje fuera de los bucles; inicio, salida y avance.
- `app/modules/taller/services/averias_service.py`: alta de falla, reparación, incompletitud, reapertura y repuestos.
- `app/modules/taller/services/cierre_service.py` y `app/modules/taller/utils.py`: estado y cierre.
- `app/modules/taller/services/solicitud_service.py`: resumen de reporte agregado.
- `app/modules/formularios/services/formulario_pauta_service.py`: pauta.
