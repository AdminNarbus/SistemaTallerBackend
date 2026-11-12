# Motivos del cambio de neumáticos: contexto para frontend

El formulario debe ofrecer tres motivos rápidos y permitir escribir cualquier
otro motivo. El campo `motivo` del backend sigue siendo texto libre.

## Opciones del formulario

| Opción visible | Texto que se envía en `motivo` |
| --- | --- |
| Reventó | `Reventó` |
| Se desinfló | `Se desinfló` |
| Pinchazo | `Pinchazo` |
| Otro | El texto escrito por el usuario, quitando espacios al inicio y al final. |

Cambiar la opción «Reventón» por «Reventó». Los demás motivos, por ejemplo
«Desgaste», «Miguelitos» o «Cambio preventivo», se ingresan mediante «Otro».

Cuando se elija «Otro», mostrar un campo **Especifica el motivo**. Para enviar
esa opción, exigir que el texto tenga contenido después de `trim()` y enviar
únicamente lo escrito: la palabra «Otro» es una opción de interfaz.

## Contrato vigente

`POST /api/v1/formularios/neumaticos`

Se mantiene el envío con `multipart/form-data`, la autenticación y los campos
existentes. Solo cambia cómo el frontend construye el valor de `motivo`.
El backend acepta un string opcional; no existe un enum ni un catálogo cerrado
de motivos y no se necesita una migración para implementar este selector.

Ejemplo para integrar en el `FormData` existente:

```ts
type MotivoSeleccionado = 'Reventó' | 'Se desinfló' | 'Pinchazo' | 'Otro';

const motivo = seleccion === 'Otro' ? motivoLibre.trim() : seleccion;
// Validar que exista una selección y que «Otro» tenga texto antes de enviar.
formData.set('motivo', motivo);
```

## Listado, filtros y valores históricos

Mostrar el texto recibido de la API. Conservar los motivos libres aunque no
coincidan con las tres opciones rápidas.

El reporte conservado en Neon (ID 513, bus 377, rueda 6, usuario 151) tiene
actualmente `motivo: "Reventón"`. Para mostrarlo y filtrarlo con la nueva
terminología, el frontend puede tratar el valor histórico exacto `Reventón`
como `Reventó`, sin sustituir coincidencias parciales en textos libres.
Esta equivalencia de presentación no modifica el dato persistido.

Si existe edición o precarga de motivos, reconocer las tres opciones rápidas
y la equivalencia histórica anterior. Para cualquier otro valor, seleccionar
«Otro» y precargar el texto completo en el campo libre.

## Criterios de aceptación

- Seleccionar cada motivo rápido envía exactamente el texto de la tabla.
- «Otro» permite enviar cualquier motivo escrito y rechaza texto vacío.
- Cambiar de «Otro» a un motivo rápido envía el motivo seleccionado.
- Los textos libres se muestran completos en el listado.
- El registro histórico «Reventón» puede verse como «Reventó» y aparecer al
  filtrar por esa opción.
- Se conserva el contrato multipart del formulario existente.
