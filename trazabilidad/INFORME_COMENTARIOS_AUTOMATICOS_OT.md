# Informe de comentarios automáticos de una OT

Fecha de revisión: 13 de octubre de 2026.

> Informe del comportamiento previo a la simplificación solicitada posteriormente. El contrato y los textos actuales están documentados en [GUIA_COMENTARIOS_BREVES_Y_ASIGNACION_GRUPAL.md](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/trazabilidad/GUIA_COMENTARIOS_BREVES_Y_ASIGNACION_GRUPAL.md). Las referencias de líneas de este informe corresponden al código revisado antes de esos cambios.

## Alcance y resultado

Revisión estática del código actual del workspace, incluidos los cambios locales que estaban presentes al comenzar. Se revisaron los productores de `TallerSolicitudComentario` en `app`, sus condiciones, servicios delegados, rutas y pruebas relacionadas. No se modificó la lógica de la aplicación ni se consultaron registros de producción. Las líneas corresponden a esta revisión y pueden desplazarse con futuras ediciones.

Hay 14 flujos que construyen comentarios automáticos, con variantes según la acción, el estado y los participantes. Los textos se generan principalmente en los servicios, no en los routers. Cada apartado indica el mensaje, la condición, el propósito y su ubicación exacta. El propósito es una interpretación funcional del comportamiento del código.

Los valores entre llaves representan datos variables; el resto reproduce el texto del mensaje. Las extensiones opcionales se agregan solo cuando hay texto no vacío después de `strip()`, salvo donde se señala otra condición.

## 1. Reportar nuevas fallas en una OT existente

Función: `SolicitudService.create_solicitud`. Tipo: `SISTEMA`.

Mensaje:

> {creador_nombre o Usuario} reportó {cantidad} nueva(s) falla(s).

Se añade ` Detalle: {descripcion_general}` cuando existe una descripción general no vacía.

**Cuándo:** al registrar una solicitud que se incorpora a una OT activa del mismo bus, en la rama `not es_nueva_ot`. La cantidad es el número de detalles efectivamente procesados.

**Por qué:** deja evidencia de quién añadió un reporte a una OT que ya existía. Es un resumen del reporte; no enumera los nombres de las fallas añadidas.

**Código:** [solicitud_service.py:527](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/solicitud_service.py:527). Extensión en la línea 529; creación del comentario en la línea 532.

**Particularidad:** una OT nueva no recibe este mensaje. En su creación se registran eventos de falla y un evento de estado `CREACION`, pero no un comentario automático de creación. Esta rama tampoco exige una cantidad mayor que cero para escribir el resumen.

## 2. Tomar una OT e iniciar los trabajos

Función: `CuadrillaService.tomar_trabajo`. Tipo: `ASIGNACION`.

| Condición | Mensaje base | Código |
| --- | --- | --- |
| La OT tiene detalles de falla | `{mec_nom} inició los trabajos de esta OT atendiendo las fallas: {fallas_str}` | [cuadrilla_service.py:137](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cuadrilla_service.py:137) |
| La OT no tiene detalles | `{mec_nom} inició los trabajos de esta OT` | [cuadrilla_service.py:139](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cuadrilla_service.py:139) |

Extensiones, en este orden:

- Si se obtuvieron nombres de colaboradores: `, junto al equipo: {nombres}`. Línea 142.
- Si se envía `comentario_inicial`: `. Nota: {comentario_inicial}`. Línea 145.

**Por qué:** registra quién tomó el trabajo y con quién. La acción desactiva las presencias anteriores, crea las nuevas y pasa la OT a `EN_REPARACION`, asegurando el ingreso al taller.

**Particularidad:** las fallas del mensaje son todos los detalles de la OT; no se filtran aquí por pendientes o resueltas. Tomar la OT crea presencia en el equipo; esta función no crea asignaciones individuales a cada falla.

## 3. Autoasignarse fallas específicas

Función: `CuadrillaService.autoasignar_fallas`. Tipo: `ASIGNACION`.

Mensaje:

> {mec_nom} inició trabajo en las fallas: {fallas_str}

Extensiones:

- Con colaboradores cuyos nombres se pudieron obtener: `, junto a {nombres}`.
- Con `dto.comentario`: `. Nota: {comentario}`.

**Cuándo:** se selecciona al menos una falla válida y se supera la validación de ocupación por otros mecánicos. El comentario se escribe incluso si las asignaciones solicitadas ya estaban activas y no fue necesario crear otras.

**Por qué:** identifica las fallas tomadas y los participantes. Si la OT está `REPORTADO`, `PENDIENTE` o `LIBERADO`, pasa a `EN_REPARACION`.

**Código:** [cuadrilla_service.py:604](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cuadrilla_service.py:604). Colaboradores en la línea 602; nota en la línea 606.

## 4. Asignar fallas desde supervisión

Función: `CuadrillaService.asignar_fallas_supervisora`. Tipo: `ASIGNACION`.

Mensaje:

> {sup_nom} asignó las fallas [{fallas_str}] al mecánico {mec_nom}

Con comentario se añade `. Nota: {comentario}`.

**Cuándo:** supervisión asigna una selección válida de fallas a un mecánico.

**Por qué:** registra al autor de la asignación, las fallas y el destinatario. Puede crear la presencia del mecánico y pasar la OT a `EN_REPARACION`.

**Código:** [cuadrilla_service.py:751](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cuadrilla_service.py:751). Nota en la línea 753.

## 5. Retirarse del equipo de la OT

Función: `CuadrillaService.desasignar_mecanico`. Tipo: `SALIDA_MECANICO`.

Mensaje:

> {mec_nom} se retiró de los trabajos de la OT

Con comentario se añade `. Motivo: {comentario}`.

**Cuándo:** un mecánico con presencia activa se retira. Si no estaba activo, se rechaza la acción antes de generar el comentario.

**Por qué:** registra la salida individual. Se desactivan su presencia y sus asignaciones; si ya no quedan presencias activas, la OT pasa a `PENDIENTE`.

**Código:** [cuadrilla_service.py:316](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cuadrilla_service.py:316). Motivo en la línea 318.

## 6. Liberar el turno

Función: `CuadrillaService.liberar_turno`. Tipo: `ENTREGA_TURNO`.

Mensaje:

> {usr_nom} entregó y liberó su turno de trabajo en la OT

Con comentario se añade `. Observación: {comentario}`.

**Cuándo:** se ejecuta la entrega/liberación del turno.

**Por qué:** deja constancia de la entrega del trabajo y su observación. La implementación desactiva **toda la cuadrilla y todas sus asignaciones**, y pasa la OT a `PENDIENTE`.

**Código:** [cuadrilla_service.py:407](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cuadrilla_service.py:407). Observación en la línea 409; desactivación grupal en la línea 375.

**Hallazgo:** el texto habla de «su turno», pero el alcance real es grupal. No significa liberar físicamente el bus para operaciones.

## 7. Terminar un avance de trabajo

Función: `CuadrillaService.terminar_avance`. Tipo: `ENTREGA_TURNO`.

| Condición | Mensaje base | Código |
| --- | --- | --- |
| Más de un mecánico involucrado en las asignaciones/presencia que se terminan | `{ejecutor_nombre} finalizó avance grupal para el equipo [{mecanicos_nombres}]` | [cuadrilla_service.py:964](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cuadrilla_service.py:964) |
| Caso individual | `{ejecutor_nombre} finalizó avance de trabajo` | [cuadrilla_service.py:966](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cuadrilla_service.py:966) |

Extensiones:

- Si hay fallas en las asignaciones terminadas: ` en las fallas: {fallas_str}`. Línea 969. Sus descripciones se deduplican.
- Si hay comentario: `: {comentario}`. Línea 972.

**Por qué:** registra el término del tramo de trabajo y del tiempo de participación. Puede cerrar asignaciones de compañeros que comparten las fallas del ejecutor. Cuando no quedan presencias ni asignaciones, la OT pasa a `PENDIENTE`.

**Particularidad:** terminar avance no marca automáticamente una falla como reparada ni finaliza la OT. Puede existir un mensaje sin lista de fallas cuando solo había presencia activa.

## 8. Agregar una avería durante la atención

Función: `AveriasService.agregar_falla`.

| Condición | Mensaje | Tipo | Código |
| --- | --- | --- | --- |
| Supervisor/admin agrega una falla resuelta e indica un resolutor válido | `Supervisora {mec_nombre} agregó la avería '{falla_txt}' resuelta por el mecánico {resolutor_nombre}` | `RESOLUCION` | [averias_service.py:293](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:293) |
| Supervisor/admin agrega una falla y se ejecuta la rama de asignación | `Supervisora {mec_nombre} agregó una nueva avería: '{falla_txt}' (asignada a {asignado_nombre})` | `AVANCE` | [averias_service.py:295](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:295) |
| Supervisor/admin sin resolutor ni asignado creado por esas ramas | `Supervisora {mec_nombre} agregó una nueva avería a la orden: '{falla_txt}'` | `AVANCE` | [averias_service.py:297](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:297) |
| Actor que no es supervisor/admin | `{mec_nombre} detectó y agregó una nueva avería a la orden: '{falla_txt}'` | `AVANCE` | [averias_service.py:299](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:299) |

En la última variante, si `dto.autoasignar` es verdadero, se añade ` (autoasignada a {mec_nombre})`. Línea 301.

**Por qué:** registra el hallazgo y, cuando corresponde, quién queda asignado o quién ya lo reparó. La OT `FINALIZADO` rechaza esta acción.

**Nombre de falla:** este método construye `falla_txt` en las líneas 270–289: nombre de catálogo/categoría más descripción personalizada, solo nombre, solo descripción o `Avería general`. No usa aquí el helper común.

## 9. Cambiar el estado de una falla mediante check

Función: `AveriasService.check_detalle`. La ruta `/taller/{id}/detalles/{detalle_id}/check` permite mecánico, supervisor o admin; por eso `{actor}` no siempre representa a un mecánico.

El objetivo se obtiene de `estado`; en su ausencia, de `resuelto`; si no se indica ninguno, se usa `RESUELTA`.

### 9.1 Marcar RESUELTA

Tipo: `RESOLUCION`.

| Condición | Mensaje | Código |
| --- | --- | --- |
| Más de un nombre en las asignaciones activas de la falla | `El equipo [{nombres}] completó la reparación de la falla: '{falla_nom}' (marcado por {actor_nom})` | [averias_service.py:448](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:448) |
| Un nombre y el ID de resolutor difiere del actor | `{actor_nom} registró la reparación de la falla '{falla_nom}' por el mecánico {resolutor_nom}` | [averias_service.py:453](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:453) |
| Un nombre y el ID de resolutor coincide con el actor | `{resolutor_nom} completó la reparación de la falla: '{falla_nom}'` | [averias_service.py:455](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:455) |
| Sin nombres disponibles | `{actor_nom} completó la reparación de la falla: '{falla_nom}'` | [averias_service.py:457](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:457) |

**Por qué:** documenta la reparación y separa al actor que la registra de los participantes acreditados. Marca las asignaciones activas como resueltas y guarda resolutor y fecha.

### 9.2 Marcar INCOMPLETA

Tipo: `AVANCE`.

| Condición | Mensaje base | Código |
| --- | --- | --- |
| Más de un nombre en las asignaciones activas | `El equipo [{nombres}] marcó la falla '{falla_nom}' como INCOMPLETA` | [averias_service.py:474](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:474) |
| Cero o un nombre | `{actor_nom} marcó la falla '{falla_nom}' como INCOMPLETA` | [averias_service.py:479](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:479) |

Si hay `motivo_incompleto`, se añade ` - Motivo: {motivo}`. En la variante grupal se añade después ` (registrado por {actor_nom})`, tenga o no motivo.

**Por qué:** registra trabajo que permanece incompleto. Se retira la resolución y se limpian el resolutor y la fecha de resolución.

### 9.3 Marcar PENDIENTE

Tipo: `REAPERTURA`.

| Condición | Mensaje | Código |
| --- | --- | --- |
| Más de un nombre en las asignaciones activas | `El equipo [{nombres}] reabrió la falla: '{falla_nom}' (registrado por {actor_nom})` | [averias_service.py:496](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:496) |
| Cero o un nombre | `{actor_nom} reabrió la falla: '{falla_nom}'` | [averias_service.py:498](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:498) |

**Por qué:** documenta que la falla vuelve a requerir atención; se retiran la resolución, el resolutor, la fecha y el motivo de incompletitud.

### Extensión común del check

Se añade ` - Observación: {comentario}` en cualquiera de los tres estados. Para `INCOMPLETA`, se omite si coincide con el motivo, evitando repetir el mismo texto.

**Código:** [averias_service.py:503](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:503); concatenación en la línea 508 y persistencia en la línea 512.

**Particularidad:** no hay una comprobación que omita el comentario si el estado solicitado ya era el estado actual. Pedir `PENDIENTE` sobre una falla pendiente también produce el texto «reabrió».

## 10. Reportar falta o disponibilidad de repuesto

Función: `AveriasService.reportar_repuesto`.

| Condición | Mensaje | Tipo |
| --- | --- | --- |
| `falta_repuesto=True` | `{mec_nom} reportó FALTA DE REPUESTO para la falla: '{falla_nom}'` | `FALTA_REPUESTO` |
| `falta_repuesto=False` | `{mec_nom} reportó REPUESTO DISPONIBLE para la falla: '{falla_nom}'` | `REPUESTO_DISPONIBLE` |

Con comentario se añade ` - Detalle: {comentario}`.

**Por qué:** registra el impedimento por repuesto o su retiro. Actualiza `falta_repuesto` y `comentario_repuesto`; no cambia por sí solo el estado de reparación de la falla.

**Código:** [averias_service.py:618](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:618). Selección de texto en las líneas 614–615; detalle en la línea 620; selección de tipo en las líneas 602–603.

**Particularidades:** activar falta de repuesto en una falla resuelta se rechaza. Reenviar el mismo valor genera otro comentario. Desactivar la bandera se describe como disponibilidad, aunque el código solo comprueba la bandera recibida, no un ingreso de inventario.

## 11. Gestionar el estado de falla desde la ruta de supervisión

Función: `AveriasService.resolver_falla_supervisora`, delegada desde `SupervisionService.resolver_falla`.

### 11.1 RESUELTA

Tipo: `RESOLUCION`.

| Condición | Mensaje | Código |
| --- | --- | --- |
| Más de un nombre en el conjunto de asignados activos y mecánicos indicados | `Supervisora {sup_nom} registró la reparación de la falla '{falla_nom}' por el equipo [{mec_nom}]` | [averias_service.py:803](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:803) |
| Un nombre en ese conjunto | `Supervisora {sup_nom} registró la reparación de la falla '{falla_nom}' por el mecánico {mec_nom}` | [averias_service.py:806](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:806) |
| Sin nombres, rama defensiva | `Supervisora {sup_nom} registró la reparación de la falla '{falla_nom}'` | [averias_service.py:809](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:809) |

Con comentario se añade ` - Observación: {comentario}`. Línea 812.

**Por qué:** supervisión registra la reparación a nombre del mecánico o equipo. El conjunto incluye a los asignados activos y a los mecánicos elegidos, sin duplicar IDs. Si no hay asignaciones activas, se exige indicar al menos un mecánico. La variante sin nombres es defensiva, no el caso normal validado.

### 11.2 INCOMPLETA

Tipo: `AVANCE`.

| Condición | Mensaje base | Código |
| --- | --- | --- |
| Más de un nombre de asignados activos | `Supervisora {sup_nom} marcó la falla '{falla_nom}' del equipo [{nombres}] como INCOMPLETA` | [averias_service.py:826](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:826) |
| Cero o un nombre | `Supervisora {sup_nom} marcó la falla '{falla_nom}' como INCOMPLETA` | [averias_service.py:828](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:828) |

Se añade ` - Motivo: {motivo}` si existe. Se toma `motivo_incompleto` o, si no se proporciona, `comentario`. Esta rama no añade por separado una observación. Líneas 821 y 830.

**Por qué:** documenta la intervención administrativa que deja la falla incompleta y su justificación.

### 11.3 PENDIENTE

Tipo: `REAPERTURA`.

> Supervisora {sup_nom} reabrió la falla '{falla_nom}' (estado PENDIENTE)

Con comentario se añade ` - Observación: {comentario}`.

**Por qué:** registra la reapertura administrativa. No enumera el equipo en esta variante.

**Código:** [averias_service.py:844](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:844). Observación en la línea 846.

**Condiciones comunes:** se rechaza modificar una OT `FINALIZADO`. No se omite el comentario por solicitar el mismo estado de falla. En el código local revisado, el comentario guarda `fecha_registro=now` y `fecha_evento=fecha_cambio_estado`, pudiendo registrar una acción ocurrida antes del momento de carga. Líneas 708–709 y 851–857.

## 12. Finalizar trabajos o liberar la solicitud

Función: `CierreService.finalizar_solicitud`. `liberar_solicitud` delega a ella y usa los mismos mensajes. Tipo: `CIERRE`.

El texto se construye en `formatear_comentario_cierre`:

| Condición | Mensaje base | Código |
| --- | --- | --- |
| Se libera el bus | `{mecanico_nombre} finalizó los trabajos de la OT y liberó el bus para operaciones.` | [utils.py:121](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/utils.py:121) |
| No se libera el bus | `{mecanico_nombre} finalizó los trabajos de la OT (el bus permanece en taller).` | [utils.py:123](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/utils.py:123) |

Extensiones, en este orden:

- ` Comentario de cierre: {comentario_cierre}.` Línea 126.
- ` Motivo cierre parcial: {motivo_cierre_parcial}.` Línea 128.
- ` Justificación pauta preventiva: {motivo_incompleto_checklist}.` Línea 130.

**Por qué:** identifica al responsable del cierre del trabajo, la salida o permanencia del bus y las justificaciones aportadas.

**Condición real del estado:** si hay fallas no resueltas o con falta de repuesto, la OT queda `LIBERADO`; si no hay pendientes, queda `FINALIZADO`. Por defecto se libera el bus. Cuando no hay pendientes, se libera incluso si `liberar_bus_taller=False`. La variante «permanece en taller» corresponde al cierre con pendientes y solicitud explícita de no liberar.

**Código de decisión e invocación:** [cierre_service.py:195](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cierre_service.py:195) y [cierre_service.py:207](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cierre_service.py:207).

**Persistencia:** [taller_repository.py:1925](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/repository/taller_repository.py:1925). El repositorio recibe el texto ya construido.

**Hallazgo:** «finalizó los trabajos de la OT» también aparece cuando quedan fallas pendientes y la OT queda `LIBERADO`. La frase puede interpretarse como reparación completa, aunque el código representa el fin de esta atención. Los motivos y la pauta incompleta no bloquean el cierre: los helpers solo normalizan las justificaciones.

## 13. Cambiar administrativamente el estado de la OT

Función: `CierreService.cambiar_estado_solicitud`. Tipo: `CAMBIO_ESTADO`.

Sin motivo:

> Supervisora {sup_nom} cambió el estado de {estado_anterior} a {nuevo_estado}.

Con motivo:

> Supervisora {sup_nom} cambió el estado de {estado_anterior} a {nuevo_estado}. Motivo: {comentario}

**Cuándo:** supervisión/admin cambia el estado de la OT y supera las validaciones. Solicitar el estado actual se rechaza; reabrir una OT finalizada se bloquea si existe una OT posterior u otra activa del mismo bus.

**Por qué:** deja evidencia del autor y de la transición administrativa, con motivo opcional. También se crea un evento estructurado de estado vinculado al comentario.

**Código activo:** [cierre_service.py:465](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cierre_service.py:465). Variantes en las líneas 467 y 469.

**Duplicación:** [supervision/utils.py:106](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/supervision/utils.py:106) define `formatear_comentario_cambio_estado` con el mismo texto. La búsqueda de referencias encontró su definición y sus pruebas, pero no uso desde la ejecución de la aplicación; el servicio construye el texto directamente.

## 14. Guardar o actualizar la pauta preventiva

Función: `FormularioPautaService.guardar_respuestas_pauta`. Tipo: `CHECKLIST`.

Mensaje:

> {mec_nom} registró/actualizó {cantidad} ítem(s) de la pauta preventiva

**Cuándo:** se guarda un lote no vacío de respuestas con IDs de ítems válidos.

**Por qué:** deja evidencia de quién respondió o actualizó la pauta. La cantidad es `len(dto.respuestas)`, no el total acumulado de ítems respondidos ni el número de respuestas que cambiaron realmente.

**Código:** [formulario_pauta_service.py:103](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/formularios/services/formulario_pauta_service.py:103).

**Particularidades:** no enumera los ítems, sus estados ni sus observaciones. Reenviar el mismo lote genera otro comentario. El archivo `taller/services/pauta_service.py` es una fachada del servicio de formularios; no genera un segundo mensaje.

## Ubicación de las acciones en la API

Rutas relativas al prefijo configurado `API_V1_STR` (valor predeterminado `/api/v1`). Los aliases de supervisión y formularios delegan a los mismos servicios; no implican mensajes adicionales.

| Acción | Ruta principal |
| --- | --- |
| Crear reporte o anexarlo a una OT activa | `POST /taller/solicitudes` |
| Tomar OT | `POST /taller/{id}/tomar` |
| Autoasignarse fallas | `POST /taller/{id}/autoasignar` |
| Asignar fallas desde supervisión | `POST /taller/{id}/asignar` |
| Retirarse del equipo | `POST /taller/{id}/desasignarme` |
| Liberar turno | `POST /taller/{id}/liberar-turno` |
| Terminar avance | `POST /taller/{id}/terminar-avance` |
| Agregar avería | `POST /taller/{id}/detalles` |
| Check de falla | `PATCH /taller/{id}/detalles/{detalle_id}/check` |
| Reportar repuesto | `PATCH /taller/{id}/detalles/{detalle_id}/repuesto` |
| Gestión de falla desde supervisión | `PATCH /supervision/solicitudes/{id}/detalles/{detalle_id}/resolver`, alias `/check` |
| Finalizar/liberar solicitud | `POST /taller/{id}/finalizar` y `POST /taller/{id}/liberar` |
| Cambio administrativo de estado | `PATCH /taller/{id}/estado` |
| Guardar pauta | `POST /taller/{id}/pauta`; también `/formularios/pauta/solicitudes/{id}` |

Definición de rutas: [cuadrilla_router.py:28](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/api/cuadrilla_router.py:28), [averias_router.py:45](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/api/averias_router.py:45), [cierre_router.py:28](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/api/cierre_router.py:28), [solicitud_router.py:79](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/api/solicitud_router.py:79), [pauta_router.py:28](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/api/pauta_router.py:28), [supervision/router.py:324](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/supervision/api/router.py:324).

## Cómo se almacenan y muestran

- La tabla es `taller_solicitud_comentarios`. Guarda OT, usuario, tipo, texto, fecha de registro y, opcionalmente, fecha efectiva del evento. Modelo: [taller_solicitud_comentario.py:14](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/models/taller_solicitud_comentario.py:14).
- `TallerRepository.add_comentario` añade el objeto a la sesión; el servicio confirma la transacción. Código: [taller_repository.py:1551](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/repository/taller_repository.py:1551).
- La respuesta completa de OT contiene `comentarios`. El mapper ORM los ordena por `fecha_registro` e ID, no por `fecha_evento`. Código: [mappers.py:530](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/mappers.py:530) y línea 571.
- El check, el reporte de repuesto y la resolución de supervisión devuelven `DetalleUpdateDTO`, no toda la bitácora. El comentario se persiste igualmente y puede verse consultando el detalle completo de OT.
- Los eventos de estado y de falla son registros estructurados adicionales. No representan necesariamente un segundo comentario visible. `registrar_evento_estado` omite transiciones con estado anterior y nuevo iguales, aunque la acción ya haya creado su comentario: [trazabilidad_estados.py:28](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/trazabilidad_estados.py:28).
- En varios mensajes, el nombre de avería sale de `describir_detalle_averia`: nombre histórico/catalogado más descripción, solo nombre, solo descripción, categoría o `Avería general`. Código: [utils.py:135](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/utils.py:135).

## Acciones sin comentario automático y textos fuera del inventario

| Caso | Comportamiento observado | Código |
| --- | --- | --- |
| Crear una OT nueva | Registra evento `CREACION` y eventos de fallas, sin mensaje automático en `comentarios` | [solicitud_service.py:525](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/solicitud_service.py:525) |
| Agregar un colaborador después de iniciar el trabajo | Crea su presencia y actualiza la OT, sin comentario de incorporación | [cuadrilla_service.py:171](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cuadrilla_service.py:171) |
| Añadir comentario manual | Guarda el texto enviado, sin frase automática; admite solo imágenes y texto vacío | [cierre_service.py:77](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/cierre_service.py:77) |
| Adjuntar fotos al check o resolución | Vincula evidencia al comentario de la acción; no crea otra frase automática | [bitacora_adjuntos.py:27](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/bitacora_adjuntos.py:27) |
| Logs, excepciones, alertas de supervisión y notificaciones de tiempo real | Son otros canales, no comentarios almacenados de OT | Por ejemplo, `supervision/utils.py` y llamadas `logger.*` |

Los tipos `GENERAL` y `SUPERVISION` permitidos por el modelo no implican una plantilla automática propia. No se encontró un productor automático con tipo `SUPERVISION` en `app`.

## Hallazgos y mejoras sugeridas

1. **Precisar el alcance de liberar turno.** El mensaje individual oculta una desactivación de toda la cuadrilla. Cambiar el texto para indicar el alcance grupal, o ajustar la operación si el producto pretende una salida individual.
2. **Distinguir fin de atención y reparación completa.** El cierre dice «finalizó los trabajos» incluso con pendientes. Para `LIBERADO`, sería más claro indicar término de atención con fallas pendientes y si el bus salió del taller.
3. **Evitar comentarios de transiciones inexistentes.** El check y la resolución de supervisión pueden escribir «reabrió» sobre una falla que ya estaba pendiente. También se repiten mensajes de repuestos, pauta y autoasignación ante solicitudes equivalentes. Definir si se desea registrar cada solicitud o solo cambios efectivos.
4. **Registrar la incorporación de colaboradores.** Actualmente esta acción cambia el equipo sin un comentario que identifique quién incorporó a quién. La creación de OT tampoco tiene un comentario inicial, aunque sí un evento estructurado.
5. **Revisar la acreditación de reparación.** Los textos de equipo se construyen a partir de asignaciones activas. En supervisión se incluyen además los resolutores seleccionados. Esto acredita al conjunto de asignados, no solo a los elegidos. En el check individual, el nombre del único asignado puede sustituir al resolutor indicado en el texto, mientras el campo singular mantiene ese ID. Conviene confirmar que esta regla de corresponsabilidad es la esperada. Código: [averias_service.py:418](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:418), líneas 440–455, y [averias_service.py:734](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/averias_service.py:734).
6. **Unificar las plantillas.** Los textos están repartidos entre servicios y helpers; el helper de cambio de estado está duplicado y no se usa en el flujo activo. Centralizarlos facilitaría ajustar redacción y verificar todas las variantes.
7. **Uniformar roles y observaciones.** El literal `Supervisora` también se usa cuando actúa un admin. La asignación de supervisión no incluye ese prefijo. Una falla incompleta usa el comentario como motivo en supervisión, mientras el check común lo trata como observación separada cuando difiere del motivo. Estas diferencias deben ser conscientes.
8. **Completar resúmenes si se necesita auditoría desde la bitácora.** El reporte agregado solo cuenta fallas y la pauta solo cuenta respuestas. Sus detalles deben consultarse en otros registros. Un reporte existente puede incluso decir «0 nueva(s) falla(s)» porque esta rama no lo impide.
9. **El objetivo de mensajes sin IDs no queda garantizado en todas las rutas.** El creador de solicitudes conserva fallbacks `Avería #{falla_id}` y `Avería de categoría #{cat_id}`; esos textos pueden quedar en la descripción y reaparecer al generar mensajes posteriores. Código: [solicitud_service.py:482](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/app/modules/taller/services/solicitud_service.py:482).

## Validación y límites

Se hizo búsqueda global de constructores `TallerSolicitudComentario`, referencias de formateadores y llamadas de persistencia en `app`, y se revisaron las ramas que construyen los textos. El informe cubre los productores del código de aplicación actual; no cataloga mensajes históricos insertados por scripts, migraciones ni datos reales de una OT específica. No se inspeccionó el frontend, por lo que la presentación visual final no se ha verificado.

Existe una prueba de flujo en [test_comentarios_predeterminados.py:19](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/tests/unit/test_comentarios_predeterminados.py:19), que comprueba frases, participantes y ausencia de determinados patrones de IDs. No es una comprobación exhaustiva de todas las variantes de este inventario. También hay pruebas de supervisión, incluida fecha efectiva, en [test_supervision_api.py:10](C:/Users/Fabian/Desktop/Narbus/BackendTallerNarbus/tests/integration/test_supervision_api.py:10). Se leyeron estas pruebas; no se ejecutó la suite durante esta revisión estática.
