# Historial de estados de OT

## Persistencia y operación

La revisión `024_historial_estados_ot`, posterior a `023_auditoria_inmutable`, crea `taller_solicitud_estado_eventos`. Cada OT nueva registra su creación y las operaciones de cierre, cambios administrativos, cuadrilla y fallas registran sus transiciones efectivas. Anexar reportes a una OT existente no registra otra creación. Repetir una operación que conserva el estado no agrega una transición.

La operación adquiere primero el bloqueo del ciclo de bus y después el de la OT. Lee el estado anterior después del bloqueo y guarda OT, comentario y evento en la misma transacción. Los cambios de fallas y repuestos también se serializan con el cierre para evitar que su validación use datos concurrentes.

Las FK son `RESTRICT`. El comentario asociado debe pertenecer a la misma OT mediante una FK compuesta. Un comentario solo puede asociarse a un evento. Un trigger reutiliza `narbus_proteger_historial()` para rechazar UPDATE y DELETE, incluso por SQL directo. Las fechas nuevas usan UTC y el nombre del actor se conserva como snapshot. El historial no se carga en los listados actuales.

`estado`, `fecha_cierre` y el responsable de cierre de la OT siguen representando su situación actual. Las estadías siguen siendo la fuente de telemetría. El historial permite consultar finalizaciones con `estado_nuevo = 'FINALIZADO'` y reaperturas con `estado_anterior = 'FINALIZADO'` y un estado nuevo distinto.

## Contrato HTTP

`GET /api/v1/taller/{id}/historial-estados?skip=0&limit=20`

Requiere un usuario autenticado, igual que el detalle de OT. `skip` es no negativo; `limit` admite de 1 a 100, con valor predeterminado 20. Devuelve una lista ordenada por `fecha_evento`, luego `id`, ascendentes, y la cabecera `X-Total-Count`. Devuelve `404` si la OT no existe. Una OT sin eventos devuelve una lista vacía.

Ejemplo de evento:

```json
{
  "id": 30,
  "solicitud_id": 123,
  "tipo_evento": "CAMBIO_ESTADO",
  "estado_anterior": "FINALIZADO",
  "estado_nuevo": "PENDIENTE",
  "usuario_actor_id": 4,
  "actor_nombre_snapshot": "Ana Pérez",
  "fecha_evento": "2026-10-06T19:00:00Z",
  "motivo": "Revisión adicional",
  "comentario_id": 50,
  "origen": "OPERACION"
}
```

Tipos: `CREACION`, `CAMBIO_ESTADO`, `CIERRE_HISTORICO`. Orígenes: `OPERACION`, `BITACORA`. Los campos `usuario_actor_id`, `motivo` y `comentario_id` pueden ser nulos. La creación tiene estado anterior nulo. Los cierres históricos ambiguos tienen ambos estados nulos y nunca cuentan como finalizaciones confirmadas.

## Importación histórica

```powershell
python -m scripts.importar_historial_estados_ot
python -m scripts.importar_historial_estados_ot --aplicar --batch-size 500
```

La primera orden es una simulación en transacción READ ONLY. La segunda inserta por lotes, confirmando cada lote. Solo procesa comentarios hasta el ID máximo observado al comenzar y puede reanudarse sin duplicados gracias a la unicidad de `comentario_id`.

Los comentarios `CAMBIO_ESTADO` con el formato canónico explícito recuperan los dos estados y el motivo. Los comentarios `CIERRE` reconocibles se importan como `CIERRE_HISTORICO`, porque el mismo texto se utiliza para cierres completos y parciales. Los textos desconocidos se omiten. Se conservan la fecha original, el actor disponible y el comentario fuente; no se modifican comentarios, estados actuales ni protecciones de la BD.

El reporte contiene `importados`, `candidatos`, `ya_existentes`, `omitidos` y `ambiguos`. `ambiguos` cuenta únicamente los candidatos nuevos de esa ejecución. El historial antiguo puede estar incompleto; no se inventan eventos para completar huecos.

## Despliegue y validación

Verificar la revisión de cada entorno y respaldarlo antes del despliegue. Aplicar la cadena Alembic, desplegar el backend que registra eventos y ejecutar la simulación e importación histórica:

```powershell
alembic current
alembic upgrade head
alembic check
python -m scripts.importar_historial_estados_ot
python -m scripts.importar_historial_estados_ot --aplicar
python -m scripts.verificar_integridad_bd
```

Para validar sin modificar la BD de la aplicación:

```powershell
python -m scripts.validar_migraciones_postgres
```

El validador solo permite localhost, copia mediante SELECT los datos a una BD desechable y prueba upgrade/check, restricciones, inmutabilidad, importación idempotente, rollback, cierre batch y concurrencia entre dos sesiones. Después prueba downgrade/upgrade/check y elimina únicamente esa BD desechable. La auditoría de integridad añade checks de estados, FK, comentarios duplicados y presencia del trigger para entornos que ya tienen la tabla nueva.

El downgrade de 024 elimina la tabla de eventos y sus datos; no elimina la función compartida de protección ni restaura cambios de negocio. Evitar ejecutarlo con tráfico de escritura y conservar el respaldo.

En esta implementación, la BD local fue respaldada en `backups/integridad_20261006T192611558612Z.json` y migrada a 024. Se importaron 11 antecedentes: 6 cambios explícitos y 5 cierres ambiguos; una segunda ejecución insertó cero. La auditoría pasó. Producción no fue modificada.
