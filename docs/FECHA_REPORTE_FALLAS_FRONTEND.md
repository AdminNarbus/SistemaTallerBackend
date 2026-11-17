# Fecha de reporte al crear una falla desde supervisión

## Contrato

`POST /api/v1/supervision/solicitudes/{id}/detalles`

Requiere token de **SUPERVISOR** o **ADMIN**. Devuelve **201** con `SolicitudDTO`.
El cuerpo existente admite ahora `fecha_reporte`, opcional y nullable:

```json
{
  "nombre": "Fuga de refrigerante detectada el martes",
  "fecha_reporte": "2026-11-10T09:30:00-03:00"
}
```

Se conserva la posibilidad de asignar inmediatamente con
`mecanico_asignado_id`, o crear como resuelta con `resuelto: true` y
`mecanico_resolvio_id`, bajo las reglas existentes. La fecha indicada solo
afecta al reporte, no a la asignación ni a la resolución.

| Campo | Significado |
| --- | --- |
| `detalles[].fecha_reporte` | Fecha real indicada por el supervisor, normalizada a UTC. |
| `detalles[].fecha_creacion` | Momento automático en que la falla se ingresó al sistema. |
| Evento `REPORTADA`: `fecha_evento` | Fecha de reporte indicada. |
| Evento `REPORTADA`: `fecha_registro` | Momento automático de inserción del evento. |

Los campos de respuesta ya existían. Se utiliza la columna existente:
**no requiere migración**. Los registros anteriores se conservan.

## Comportamiento y validaciones

- Omitir `fecha_reporte` o enviar `null` usa el momento actual del servidor,
  igual que antes.
- Debe ser un datetime ISO 8601 con zona horaria: `Z` o un offset como `-03:00`.
  Una fecha sola, un datetime sin zona o un valor inválido devuelve **422**.
- Una fecha futura devuelve **422** con
  `error.code: "BUSINESS_RULE_VIOLATION"` y
  `error.message: "La fecha de reporte no puede ser futura"`.
- SUPERVISOR y ADMIN pueden indicar fechas anteriores, incluso anteriores
  a la creación de la OT, para registrar un hallazgo conocido previamente.
- La ruta compartida `POST /api/v1/taller/{id}/detalles` admite el mismo campo,
  con la misma restricción de rol: un MECANICO que lo envía con valor recibe
  **403** (`FORBIDDEN`). Omitirlo o enviar `null` conserva su flujo actual.
- La OT debe admitir nuevas fallas según las reglas existentes; una OT
  finalizada sigue rechazándolas. No se agrega edición de fechas de fallas existentes.

## Integración en la interfaz

1. Agregar al modal «Nueva falla» de supervisión un campo opcional
   **Fecha y hora del reporte**, con ayuda «Cuándo se detectó o reportó la falla.
   Si se deja vacío, se usa la fecha y hora actual».
2. Permitir seleccionar fecha y hora anteriores y limitar el selector al momento
   actual. El servidor realiza la validación definitiva.
3. Convertir la selección a un instante con zona antes de enviarla. Un
   `datetime-local` entrega texto sin zona: no enviarlo directamente ni agregarle
   `Z` sin conversión.
4. Mostrar **Fecha de reporte** usando `fecha_reporte ?? fecha_creacion`.
   Reservar **Ingresada al sistema** para `fecha_creacion`.
5. Mantener las acciones de asignación/resolución existentes. Actualizar la ficha
   con la respuesta y consultar el detalle de la OT para refrescar el historial.

Si la interfaz interpreta la selección en la zona local del navegador:

```ts
const payload = {
  nombre,
  ...(fechaLocal ? { fecha_reporte: new Date(fechaLocal).toISOString() } : {}),
};

await api.post(`/supervision/solicitudes/${solicitudId}/detalles`, payload);
```

Si la interfaz fija **America/Santiago** y el navegador puede estar en otra zona,
convertir la selección usando esa zona explícita con las utilidades de fechas
del frontend. No fijar `-03:00` para todo el año: debe respetarse el offset de
la fecha seleccionada.

Para mostrar las fechas en la zona del taller:

```ts
const formato = new Intl.DateTimeFormat('es-CL', {
  timeZone: 'America/Santiago',
  dateStyle: 'short',
  timeStyle: 'short',
});
const reporte = detalle.fecha_reporte ?? detalle.fecha_creacion;
const etiqueta = formato.format(new Date(reporte));
```

En el historial, usar `fecha_evento` para la cronología operacional y
`fecha_registro` para mostrar cuándo se ingresó una anotación histórica.
La aprobación, las asignaciones, la resolución, la bitácora general y
`solicitud.fecha_actualizacion` conservan sus fechas actuales automáticas.

## Verificación del frontend

- Crear una falla sin fecha: reporte y creación coinciden.
- Crear con una fecha anterior: mostrar esa fecha como reporte y la actual como ingreso.
- Repetir con asignación y con resolución: ambas acciones ocurren en el momento actual.
- Intentar enviar una fecha futura o sin zona: mostrar el error 422.
- Verificar que el mecánico no vea el campo y que el historial conserve ambas fechas.

Implementación en el backend local; su uso en otro entorno requiere desplegar
este código y realizar la integración en el repositorio del frontend.
