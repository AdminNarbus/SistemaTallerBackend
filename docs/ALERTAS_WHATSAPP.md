# Alertas por WhatsApp (Meta Cloud API)

El backend consulta el centro de alertas de supervisión y notifica
`OT_SIN_INGRESO_TALLER` y `LIBERADO_TIEMPO_EXCEDIDO`. Usa sus umbrales existentes.
No es necesario abrir el dashboard: el timer consulta al arrancar y cada cinco
minutos, mientras el proceso esté activo. El envío viene desactivado por defecto.
Al activarlo se notifican también las alertas que ya estaban activas y cumplen
la severidad mínima; no se limita a alertas generadas después de la activación.

## Configuración

1. Aplicar `alembic upgrade head` en el entorno de destino mediante el proceso
   habitual. La revisión `042_whatsapp_envios` agrega el registro de envíos.
2. Configurar una aplicación de Meta con WhatsApp, número emisor y token con
   permiso `whatsapp_business_messaging`. `WHATSAPP_PHONE_NUMBER_ID` es el ID
   del número emisor en Meta, no su teléfono. Guardar el token en el gestor de
   secretos del entorno; no incluirlo en Git ni enviarlo desde el frontend.
3. Usar la plantilla aprobada `alerta_taller_visual`, idioma `es`, con
   **cinco parámetros posicionales de cuerpo**, sin encabezados ni botones con
   variables. Nombre e idioma son configurables y deben coincidir con Meta.
4. Registrar únicamente los teléfonos internacionales de destinatarios que hayan
   autorizado estas notificaciones en `WHATSAPP_DESTINATARIOS` (separados por
   comas, máximo 20). Se acepta `+` y se elimina para enviar a Meta. Para retirar
   un destinatario, quitar su número de la configuración y reiniciar el proceso.
5. Configurar `WHATSAPP_API_VERSION` con una versión habilitada en la aplicación
   de Meta (`vNN.0`), `WHATSAPP_ACCESS_TOKEN` y `WHATSAPP_PHONE_NUMBER_ID`.
   Activar `WHATSAPP_ENABLED=true` al terminar la configuración.

Contrato de la plantilla:

| Variable | Valor |
|---|---|
| `{{1}}` | Severidad: BAJA, MEDIA, ALTA o CRITICA |
| `{{2}}` | Tipo de alerta |
| `{{3}}` | Número del bus |
| `{{4}}` | ID de la solicitud/OT |
| `{{5}}` | Mensaje del centro de alertas |

Texto de ejemplo para registrar en Meta:

```text
🚨 *ALERTA DE TALLER*

⚠️ *Severidad:* {{1}}
🏷️ *Tipo:* {{2}}
🚌 *Bus:* {{3}}
📋 *Solicitud:* {{4}}

📝 *Detalle:* {{5}}

Revisa la orden en el sistema de taller.
```

Los valores se envían sin saltos de línea ni tabulaciones, con un máximo de
500 caracteres por variable. Se usa el contrato de
[plantillas de Meta](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/messages/template/)
mediante HTTP directamente; no se instala ese SDK archivado.

`WHATSAPP_SEVERIDAD_MINIMA` filtra niveles inferiores (por defecto BAJA).
`WHATSAPP_INTERVAL_SECONDS` admite entre 60 y 86400 segundos, por defecto 300.
`WHATSAPP_TIMEOUT_SECONDS` admite entre 1 y 60 segundos, por defecto 20.
Las credenciales incompletas impiden iniciar con WhatsApp activado.

## Operación y API

`POST /api/v1/supervision/alertas/whatsapp/envios`, sin cuerpo, exige JWT de
SUPERVISOR o ADMIN y ejecuta un ciclo con los destinatarios del servidor.
No acepta teléfonos arbitrarios ni token de Meta desde el cliente. Devuelve:

```json
{
  "alertas_activas": 4,
  "aceptados": 2,
  "omitidos": 2,
  "fallidos": 0,
  "inciertos": 0,
  "reintentos_pendientes": 0
}
```

`alertas_activas` cuenta alertas antes del filtro por severidad. Los demás
contadores corresponden a pares alerta/destinatario. `omitidos` incluye los ya
reservados/enviados y reintentos cuyo plazo aún no vence. Con WhatsApp
desactivado, el POST devuelve 422 y no consulta alertas ni llama a Meta.

`GET /api/v1/supervision/alertas/whatsapp/envios?skip=0&limit=20` permite consultar
el historial, con máximo 100 registros por página, aun con el envío desactivado.
Respeta los permisos de supervisión existentes, incluida la lectura del rol
VISUAL. El historial contiene teléfonos: mantener el acceso autenticado.

## Duplicados, fallos y límites

- Una clave única persistente identifica tipo, solicitud, detalle, severidad y
  destinatario. La reserva se confirma antes de llamar a Meta. Procesos
  concurrentes y reinicios comparten la protección de la base de datos.
- La misma alerta no se repite por cambiar sus horas, mensaje o fecha de
  detección. Una severidad nueva o un destinatario nuevo genera un envío nuevo.
  Si una alerta desaparece y vuelve en la misma OT y nivel, no se vuelve a enviar.
- `ACEPTADO` significa que Meta devolvió un ID de mensaje. **No confirma entrega
  ni lectura**: esta versión no recibe webhooks de estado de Meta.
- HTTP 429 queda `REINTENTABLE`: espera al menos cinco minutos, respeta
  `Retry-After` numérico (hasta un día) y limita a tres intentos totales. Solo se
  reintenta si la alerta sigue activa y supera el filtro vigente. Los ciclos
  manuales y el timer comparten el mismo plazo y límite.
- Otros errores 4xx quedan `FALLIDO`. Corregir credenciales/plantilla antes de
  operar; no se reenvían automáticamente esos pares ya registrados.
- Timeout, fallo de red, 5xx o respuesta sin ID quedan `INCIERTO`. Una reserva
  abandonada por una caída pasa a `INCIERTO` en el siguiente ciclo, después de
  diez minutos. No se reenvían: Meta podría haber aceptado el mensaje antes del
  fallo. Revisar el registro y Meta para resolver esos casos. No se promete
  entrega exactamente una vez frente a caídas entre ambos sistemas.
- `solicitud_id` es una referencia histórica sin FK: el registro de auditoría
  del proveedor permanece independiente de la eliminación de datos operativos.
  Tokens y cuerpos de error de Meta no se guardan ni se registran en logs.

En Cloud Run, el timer requiere una instancia activa y CPU disponible fuera de
peticiones. Con escalado a cero no ejecutará a horario. Para una instalación
basada en llamadas programadas, desactivar `WHATSAPP_TIMER_ENABLED` y hacer que
el planificador invoque el POST autenticado. Configurar esa infraestructura
corresponde al despliegue.

## Verificación local

```powershell
venv/Scripts/python.exe -m pytest tests/unit/test_whatsapp_alertas_service.py tests/unit/test_whatsapp_timer.py tests/integration/test_whatsapp_alertas.py tests/migrations/test_whatsapp_envios_migration.py -q
```

Las llamadas de Meta se simulan; SQLite es desechable y la prueba PostgreSQL usa
un clúster temporal en loopback. No se envían mensajes reales durante las pruebas.
