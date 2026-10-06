# Guía Frontend: sincronización en tiempo real

## Conexión

Conectar una vez que exista una sesión válida a `wss://<backend>/api/v1/realtime/ws`.
En los primeros cinco segundos enviar:

```json
{"type":"auth","protocol_version":1,"access_token":"<access_token>"}
```

La conexión queda lista al recibir `connection.ready`. Enviar `{"type":"ping"}` cada 25 segundos y aceptar `pong`.

## Eventos

El backend entrega `resource.changed`. El mensaje no contiene la ficha completa: invalida las consultas relacionadas y vuelve a pedir el dato REST autorizado. Para `work_order`, recargar el detalle abierto y los listados de pendientes, mis trabajos y supervisión. Para `bus` o `user`, invalidar sus catálogos y vistas administrativas.

No reemplazar la respuesta de una mutación propia: esa respuesta REST es la confirmación inmediata. El evento posterior sirve para reconciliar todas las pestañas y usuarios conectados.

## Recuperación

Reconectar con backoff exponencial y jitter, hasta un máximo de 30 segundos. Ante `4401`, renovar el access token antes de reconectar; ante `4403`, cerrar la sesión. Al reconectar, volver a pedir las consultas visibles. Mantener un refetch de seguridad cada 60 segundos mientras haya una pantalla operacional abierta.

El despliegue o reinicio puede cerrar el socket con `1012`; esto es esperado y debe activar la reconexión.
