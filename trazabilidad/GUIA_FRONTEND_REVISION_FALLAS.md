# Guía frontend: revisión individual de fallas

Fecha: 2026-11-09. Contrato implementado en BackendTallerNarbus, migración `041_revision_fallas`.
Estado frontend: pendiente de implementación. Esta guía no modifica su código.

## 1. Comportamiento esperado

Una OT aceptada (`es_ot=true`) puede recibir fallas nuevas que todavía no están autorizadas para intervención. El frontend debe distinguirlas visualmente y ofrecer las acciones que permiten aprobarlas.

Hay tres conceptos independientes:

| Campo | Significado | Valores |
| --- | --- | --- |
| `solicitud.es_ot` | La solicitud ya fue aceptada como orden de trabajo. | `true` / `false` |
| `detalle.estado_revision` | La falla tiene autorización para intervenirse. | `PENDIENTE` / `APROBADA` |
| `detalle.estado` | Progreso de la reparación. | `PENDIENTE` / `INCOMPLETA` / `RESUELTA` |

Una falla puede tener `estado_revision=APROBADA` y `estado=PENDIENTE`: está autorizada, pero todavía no reparada. Aprobar no resuelve ni asigna la falla. Asignarla sí puede aprobarla en la misma operación.

## 2. Campos de respuesta y tipos

Agregar a `DetalleSolicitudDTO` en `src/types/mantencion.ts`; el alias `SolicitudDetalleDTO` debe conservarlos. Revisar también adaptadores y tipos de auditoría que copien detalles.

```ts
export type EstadoRevisionFalla = 'PENDIENTE' | 'APROBADA';

// Agregar estas propiedades a la interfaz existente.
export interface DetalleSolicitudDTO {
  // ...conservar las demás propiedades existentes
  estado_revision: EstadoRevisionFalla;
  revisado_por_id: number | null;
  fecha_revision: string | null;
}
```

Ejemplo parcial de un elemento de `SolicitudDTO.detalles`:

```json
{
  "id": 120,
  "solicitud_id": 8,
  "descripcion_personalizada": "Fuga de aire",
  "estado": "PENDIENTE",
  "resuelto": false,
  "estado_revision": "PENDIENTE",
  "revisado_por_id": null,
  "fecha_revision": null
}
```

Tras aprobar, el mismo detalle tendrá `estado_revision: "APROBADA"`, un `revisado_por_id` y una fecha ISO del servidor. El aprobador también puede ser un mecánico por autoasignación o aprobación automática de su reporte; no etiquetarlo siempre como supervisor.

No existe un campo `revisado_por_nombre` en este contrato. Resolver el nombre mediante los usuarios disponibles o mostrar el ID. Las fallas históricas migradas pueden estar aprobadas con autor y fecha nulos: mostrar «Aprobación histórica», sin inventar esos datos.

Si la respuesta omite `estado_revision` o trae un valor desconocido, mostrar «Revisión no disponible» y bloquear intervención hasta actualizar/recargar. No convertir silenciosamente el valor faltante a APROBADA ni confundirlo con PENDIENTE válido. Esto ayuda a detectar un backend aún sin actualizar.

## 3. Reglas exactas de aprobación

| Situación | Resultado |
| --- | --- |
| Conductor reporta una falla nueva, incluso en OT aceptada. | Queda PENDIENTE de revisión. |
| Mecánico reporta sin autoasignarse y sin asignaciones activas previas a fallas de esa OT. | Queda PENDIENTE. |
| Mecánico con alguna asignación activa previa a una falla de esa misma OT reporta otra. | Nueva falla APROBADA automáticamente, aunque no se autoasigne la nueva. |
| Mecánico agrega una falla con `autoasignar=true`. | Nueva falla APROBADA y asignada; no requiere asignación previa. |
| Mecánico se autoasigna fallas existentes seleccionadas. | Esas fallas quedan APROBADA y asignadas. No se aprueban las no seleccionadas. |
| Supervisor/admin asigna fallas a mecánicos. | Se aprueban las seleccionadas. |
| Supervisor/admin reporta una falla. | Se considera APROBADA. |
| Supervisor/admin da visto bueno individual. | Se aprueba esa falla, sin asignarla ni repararla. |
| Se aprueba inicialmente una solicitud como OT o se toma por primera vez. | Se aprueban sus fallas actuales. Si la conversión ocurre por asignación selectiva, solo se aprueban las seleccionadas. |
| Se vuelve a aprobar/tomar una cabecera que ya es OT. | No aprueba automáticamente sus reportes posteriores. |

Tener presencia en la cuadrilla o haber trabajado antes no equivale por sí solo a tener una asignación activa a una falla. El backend calcula la regla; usar siempre su respuesta para decidir el resultado.

## 4. Aprobar una falla desde supervisión

```http
PATCH /api/v1/supervision/solicitudes/{ot_id}/detalles/{detalle_id}/aprobar
Authorization: Bearer <sesión actual>
```

Sin body. Devuelve `200` con la **OT completa (`SolicitudDTO`)**, no un detalle suelto.

Condiciones: supervisor/admin activo, `es_ot=true`, OT distinta de FINALIZADO y detalle perteneciente a la OT. LIBERADO permite aprobación. VISUAL no puede aprobar.

Ejemplo de servicio siguiendo el cliente Axios del frontend:

```ts
import { apiClient } from '../api/apiClient';
import type { SolicitudDTO } from '../types/mantencion';

export async function aprobarFalla(
  otId: number,
  detalleId: number,
): Promise<SolicitudDTO> {
  const { data } = await apiClient.patch<SolicitudDTO>(
    `/api/v1/supervision/solicitudes/${otId}/detalles/${detalleId}/aprobar`,
  );
  return data;
}
```

Reemplazar/actualizar la OT almacenada con esa respuesta, incluyendo detalles, comentarios y fecha de actualización; invalidar listados relacionados. Mostrar «Falla aprobada». Deshabilitar el botón mientras la petición está en curso y conservar la falla si falla la solicitud. Evitar marcarla aprobada de forma optimista.

La aprobación es idempotente: repetirla conserva el primer aprobador y fecha y no duplica el comentario. No requiere UUID de operación. Registra en bitácora `Falla #{id} aprobada por supervisión.` y emite un evento `resource.changed` de `work_order`, con `action=updated`; usar la invalidación de tiempo real existente para otras vistas.

## 5. Asignación: mantener las rutas existentes

No es necesario llamar primero al endpoint de aprobación: la asignación aprueba en la misma transacción.

Autoasignación (mecánico; la ruta también admite admin):

```http
POST /api/v1/taller/8/autoasignar
Content-Type: application/json

{"detalles_ids":[120,121],"comentario":"Inicio de atención"}
```

Asignación por supervisión/admin:

```http
POST /api/v1/taller/8/asignar
Content-Type: application/json

{"detalles_ids":[120,121],"mecanicos_ids":[2,3]}
```

Ambas devuelven `SolicitudDTO`. La pertenencia, disponibilidad y demás restricciones de asignación siguen aplicando: la revisión pendiente no las elimina.

**No quitar las fallas PENDIENTE de revisión del selector de autoasignación.** Esa selección es justamente una forma válida de aprobarlas. Rotular la acción «Asignarme y aprobar seleccionadas» cuando corresponda, y enviar únicamente los IDs elegidos.

## 6. Agregar o reportar fallas

El endpoint directo para mecánico/supervisión/admin es:

```http
POST /api/v1/taller/8/detalles
Content-Type: application/json

{"nombre":"Ruido en dirección","autoasignar":false}
```

Para mecánicos ofrecer «Reportar» y «Reportar y asignarme», enviando `autoasignar:false` o `true` explícitamente. **El default del backend es `true`**: omitirlo no sirve para reportar sin asignarse.

Con `false`, el backend todavía puede aprobar automáticamente si ese mecánico ya tiene alguna falla asignada activamente en la misma OT. Usar el valor devuelto para el mensaje final: «Falla reportada, pendiente de revisión» o «Falla reportada y aprobada».

El conductor utiliza su formulario existente `POST /api/v1/taller/solicitudes` con `detalles`; no habilitarle el endpoint directo de mecánicos. Si el reporte se incorpora a una OT activa, la nueva falla queda pendiente de revisión.

No enviar `estado_revision`, `revisado_por_id` ni `fecha_revision` desde formularios de ingreso o edición. Son campos determinados por el servidor. Editar el texto de una falla tampoco constituye aprobación: usar visto bueno o asignación.

## 7. Presentación y permisos de acciones

En el detalle de OT, separar visualmente «Pendientes de revisión» y «Fallas aprobadas», o usar un filtro y un distintivo claro. Mantener los reportes pendientes visibles para supervisión y para asignación del mecánico. No ocultarlos simplemente por no pertenecer aún al trabajo autorizado.

| Acción | PENDIENTE de revisión | APROBADA |
| --- | --- | --- |
| Consultar descripción y autor del reporte | Sí, según permisos existentes. | Sí. |
| Visto bueno supervisor/admin | Sí, si es OT aceptada y abierta. | Mostrar estado aprobado; no hace falta repetir. |
| Seleccionar para asignar/autoasignarse | Sí, sujeto a permisos y disponibilidad existentes. | Sí, con las mismas restricciones. |
| Registrar resultado, check o reparación | Bloquear. | Aplicar permisos normales, asignación y estado de OT. |
| Reportar falta de repuesto | Bloquear. | Aplicar reglas existentes. |
| Registrar o anular consumos de repuestos | Bloquear. | Aplicar reglas existentes de autoría y asignación. |
| Consultar historial de repuestos existente | Conservar consulta según permisos. | Conservar consulta según permisos. |

Para una OT FINALIZADO no mostrar acciones de aprobación ni de intervención. Para `es_ot=false`, orientar a la aprobación inicial o asignación existente; el endpoint individual exige una OT ya aceptada. No usar `es_ot` como sustituto del estado de revisión de cada detalle.

VISUAL permanece en consulta: sin botones de aprobación, asignación, modificación ni registro. El conductor reporta; no recibe acciones de aprobación.

Los modales de resultados y repuestos deben volver a comprobar la revisión del detalle seleccionado al cambiar el selector. Si el modal agrega repuestos a diferentes fallas, mostrar por qué la falla seleccionada requiere aprobación en lugar de permitir enviar una petición destinada a fallar.

## 8. Contadores y sincronización de estado

Los contadores existentes (`total_fallas`, `fallas_pendientes`, etc.) siguen contando reportes y no son contadores de revisión. `fallas_pendientes` se refiere al progreso operativo, no al visto bueno.

En el detalle completo, calcular por separado:

```ts
const porRevisar = ot.detalles.filter(d => d.estado_revision === 'PENDIENTE');
const aprobadas = ot.detalles.filter(d => d.estado_revision === 'APROBADA');
```

No anunciar que el backend devuelve `fallas_por_revisar`: ese agregado no existe. No calcular un total global de revisión a partir de una página parcial ni de resúmenes sin detalles.

Tras aprobar/asignar/agregar, conservar la respuesta autoritativa del servidor y actualizar todas las vistas que comparten la OT. Revisar normalizadores, mappers y cachés: un mapper que reconstruye detalles sin copiar los tres campos pierde la revisión aunque el endpoint la devuelva correctamente. `DetalleUpdateDTO` de resultados no debe interpretarse como una nueva aprobación ni borrar los campos de revisión ya conocidos.

## 9. Errores y mensajes

| HTTP | Manejo recomendado |
| --- | --- |
| 401 | Recuperar sesión mediante el flujo actual. |
| 403 | Informar falta de permisos; no cambiar el estado local. |
| 404 | OT/falla inexistente o fuera del contexto: recargar y no conservar una selección inválida. |
| 422 | Mostrar `error.message`; puede faltar aprobación inicial, estar finalizada la OT o requerir revisión la falla. |
| Error de red | Mantener datos y permitir reintentar. Una aprobación individual repetida es segura. |

Respuesta de regla de negocio, por ejemplo:

```json
{"error":{"code":"BUSINESS_RULE_VIOLATION","message":"La falla debe estar aprobada antes de intervenirla; asígnela o solicite el visto bueno de supervisión","detail":null}}
```

No mostrar éxito si la petición falla. Un estado local desactualizado puede permitir abrir un modal antes de que otro usuario cierre la OT; conservar las validaciones del servidor y recargar ante un rechazo.

## 10. Puntos de implementación en ProtoNeumaticos

Rutas de referencia dentro del repositorio frontend hermano, inspeccionadas al preparar esta guía:

- `src/types/mantencion.ts`: contrato `DetalleSolicitudDTO` y alias.
- `src/types/supervision.ts`: tipos derivados de auditoría que contengan fallas.
- `src/services/`: agregar el servicio de aprobación con `apiClient`; reutilizar los servicios actuales de asignación y reporte.
- `src/supervisores/supervision/tabs/ModalDetalleFallaSupervision.tsx`: distintivo y acción de aprobación.
- `src/supervisores/supervision/tabs/ModalResolverAveriaSupervision.tsx`: bloqueo de resultados sin revisión.
- `src/mecanicos/revisiones/modales/ModalAutoasignarFallas.tsx`: permitir seleccionar pendientes de revisión.
- `src/mecanicos/revisiones/modales/ModalAgregarFalla.tsx`: elección explícita de autoasignación.
- `src/mecanicos/revisiones/hooks/useOrdenesMecanico.ts` y `ordenesMecanicoState.ts`: preservar campos al normalizar/actualizar estado.
- `src/components/Repuestos/ModalRepuestosFalla.tsx` y `ModalRepuestosSupervisionOT.tsx`: habilitación por revisión y contexto.

Buscar adicionalmente todas las copias/adaptaciones de `detalles` y todos los lugares que habilitan controles basándose solo en `es_ot` o `estado`.

## 11. Checklist de aceptación frontend

- [ ] Conductor agrega a una OT aceptada: se ve PENDIENTE de revisión, sin confundirse con reparación pendiente.
- [ ] Mecánico sin asignaciones reporta con `autoasignar:false`: queda pendiente.
- [ ] Mecánico sin asignaciones reporta con `true`: queda aprobada y asignada.
- [ ] Mecánico ya asignado reporta con `false`: se muestra la aprobación automática devuelta.
- [ ] Autoasignar una de dos fallas pendientes aprueba solo la seleccionada; la otra sigue visible y pendiente.
- [ ] Supervisión puede aprobar individualmente en OT PENDIENTE, EN_REPARACION y LIBERADO.
- [ ] Asignar por supervisión aprueba solo las seleccionadas, sin petición previa de visto bueno.
- [ ] Aprobar inicialmente/tomar una solicitud aprueba su alcance inicial; volver a tomar una OT aceptada no aprueba reportes posteriores.
- [ ] Pendiente de revisión no permite resultados, falta de repuestos ni altas/anulaciones de consumos.
- [ ] Aprobar no resuelve la falla ni cambia por sí solo el estado liberado de la OT.
- [ ] Repetir aprobación conserva fecha/autor y no duplica bitácora.
- [ ] Recargar navegador conserva revisión; otra pestaña se actualiza por la invalidación de tiempo real existente.
- [ ] Falla histórica APROBADA con autor/fecha nulos se muestra correctamente.
- [ ] VISUAL y conductor no ven acciones de aprobación; FINALIZADO no ofrece intervención.
- [ ] Error del servidor no produce éxito ni aprobación optimista.
- [ ] Se verifican escritorio y móvil, incluyendo modales y selección de falla en repuestos.

## 12. Dependencia de despliegue

El backend destino debe incluir código actualizado y migración 041 antes de habilitar estas acciones. Esta guía documenta el contrato del checkout local; no acredita que esté desplegado en producción. No crear estados RECHAZADA ni acciones de rechazar/revertir revisión: no existen en la implementación actual.

Referencias backend: `docs/REVISION_INDIVIDUAL_FALLAS.md`, `app/modules/taller/services/revision_falla_service.py`, `app/modules/taller/services/aprobacion_ot_service.py`, `app/modules/taller/api/cuadrilla_router.py` y `tests/integration/test_revision_fallas.py`.
