# Guía frontend: fotos en bitácora de OT

## Objetivo

La bitácora de cada OT permite que mecánicos, supervisores y administradores publiquen comentarios con hasta **3 imágenes**. Las fotos quedan asociadas al evento exacto que las produjo: un mensaje manual o un cambio de estado de una falla.

Los conductores pueden visualizar el historial si ya tienen acceso a la OT, pero no pueden publicar en esta bitácora técnica.

## Diseño sugerido

En el compositor de mensajes, el control de imágenes debe ser un botón pequeño, secundario al textarea:

```text
+----------------------------------------------------------+
| Escribe un hallazgo o comentario...                      |
+----------------------------------------------------------+
| [ 📎 ]  2 fotos seleccionadas                 [Enviar]   |
+----------------------------------------------------------+
```

- Usar un icono de imagen o clip (`ImagePlus`, `Paperclip`, etc.) de aproximadamente 32–36 px, con tooltip **“Adjuntar fotos”**.
- El botón abre un selector con `accept="image/jpeg,image/png,image/webp"` y `multiple`.
- No presentarlo como acción principal: el botón `Enviar` conserva el énfasis visual.
- Mostrar miniaturas removibles antes del envío y el contador `0/3`, `1/3`, etc.
- Deshabilitar el botón de adjuntos al llegar a tres imágenes y mostrar un mensaje claro si el usuario intenta exceder el límite.
- Permitir enviar solo fotos, solo texto o ambos; bloquear el envío únicamente si no hay texto ni archivos.

## Publicar un comentario en la bitácora

### Endpoint

`POST /api/v1/taller/{solicitudId}/comentarios`

### Comentario sin imágenes

Se mantiene el contrato JSON existente:

```ts
await api.post(`/api/v1/taller/${solicitudId}/comentarios`, {
  tipo: 'GENERAL',
  comentario: texto,
});
```

### Comentario con imágenes

Usar `FormData`. Cada archivo debe agregarse bajo el mismo nombre `fotos`:

```ts
const form = new FormData();

if (texto.trim()) form.append('comentario', texto.trim());
form.append('tipo', 'GENERAL');
imagenes.forEach((imagen) => form.append('fotos', imagen));

await api.post(`/api/v1/taller/${solicitudId}/comentarios`, form);
```

No fijar manualmente el encabezado `Content-Type`: el cliente HTTP debe incluir el boundary de `multipart/form-data`.

La respuesta incluye el comentario creado y sus adjuntos:

```ts
type AdjuntoBitacora = {
  id: number;
  solicitud_id: number;
  detalle_id: number | null;
  usuario_id: number | null;
  comentario_id: number;
  url: string;
  original_filename: string | null;
  size_bytes: number | null;
  content_type: string | null;
  fecha_creacion: string | null;
};

type ComentarioCreado = {
  comentario_id: number;
  solicitud_id: number;
  usuario_id: number;
  usuario_nombre: string | null;
  tipo: string;
  comentario: string;
  fecha_registro: string;
  adjuntos: AdjuntoBitacora[];
};
```

Tras una respuesta exitosa, agregar el comentario devuelto al estado local de la bitácora y limpiar textarea, miniaturas y selector de archivos.

## Adjuntar evidencia al cambiar una falla

Los adjuntos son opcionales al marcar una falla como `PENDIENTE`, `INCOMPLETA` o `RESUELTA`. No se crea un mensaje manual adicional: las fotos se vinculan al evento automático que registra el cambio.

### Taller

`PATCH /api/v1/taller/{solicitudId}/detalles/{detalleId}/check`

```ts
const form = new FormData();
form.append('estado', 'INCOMPLETA');
form.append('motivo_incompleto', motivo.trim()); // opcional
form.append('comentario', observacion.trim());   // opcional
imagenes.forEach((imagen) => form.append('fotos', imagen));

await api.patch(
  `/api/v1/taller/${solicitudId}/detalles/${detalleId}/check`,
  form,
);
```

### Supervisión

Usar cualquiera de estos alias:

- `PATCH /api/v1/supervision/solicitudes/{solicitudId}/detalles/{detalleId}/resolver`
- `PATCH /api/v1/supervision/solicitudes/{solicitudId}/detalles/{detalleId}/check`

El formato es el mismo. Para `RESUELTA`, mantener los campos existentes de mecánico resolutor (`mecanico_id` o valores repetidos de `mecanicos_ids`) cuando correspondan.

## Mostrar el historial

Al obtener una OT, cada elemento de `comentarios` contiene `adjuntos`:

```ts
type ComentarioBitacora = {
  id: number;
  usuario_nombre: string | null;
  tipo: string;
  comentario: string;
  fecha_registro: string;
  adjuntos: AdjuntoBitacora[];
};
```

Renderizar las imágenes debajo del texto del evento, como una cuadrícula de miniaturas. Cada miniatura debe abrir la URL entregada por el backend en un modal o visor de imagen. No construir URLs locales ni almacenar manualmente rutas: usar siempre `adjunto.url`.

Las evidencias siguen apareciendo además en `solicitud.evidencias` por compatibilidad. Para el chat, la fuente principal debe ser `comentario.adjuntos`, ya que conserva el contexto de quién, cuándo y por qué se adjuntó cada foto.

## Validaciones y manejo de errores

- Máximo: 3 imágenes por acción.
- Formatos: JPG, JPEG, PNG y WebP.
- El tamaño máximo por archivo depende de la configuración del backend; mostrar el mensaje devuelto por la API si se rechaza un archivo.
- Si la API devuelve `403`, ocultar o deshabilitar el compositor para usuarios sin rol `MECANICO`, `SUPERVISOR` o `ADMIN`.
- Si falla el envío, conservar texto y miniaturas para permitir reintentar.
- No implementar edición o eliminación de comentarios ni de fotos: la bitácora es inmutable.
