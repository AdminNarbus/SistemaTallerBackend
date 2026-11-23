# Avisos de solicitudes de conductores por WhatsApp

Cuando un conductor registra un reporte mediante `POST /api/v1/taller/solicitudes`, se guarda un aviso por destinatario en la misma transacción. Esto incluye reportes añadidos a una solicitud existente. Un trabajador del backend despacha los avisos pendientes sin retrasar la respuesta HTTP.

El aviso contiene el nombre del conductor, el bus, el número de solicitud y hasta tres nombres de fallas; si no hay fallas, usa la descripción general. La plantilla predeterminada `narbus_reporte_fallas_visual`, idioma `es_CL`, usa cuatro variables en ese orden. Cada texto se limita a 450 caracteres; el nombre, a 100. La plantilla debe estar disponible y aprobada en la cuenta y el número emisor que se usen antes de activar el servicio.

Los avisos ya encolados con el formato anterior de tres variables siguen usando `narbus_fallas` en `es_CL`. Si se configura explícitamente `narbus_fallas`, los reportes nuevos se convierten a ese formato anterior.

## Configuración

1. Aplicar las migraciones hasta `043_whatsapp_solicitudes` en la base del entorno, siguiendo el procedimiento de despliegue.
2. Configurar `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` y `WHATSAPP_API_VERSION` para Meta. Compartidas con las alertas; no es necesario activar el servicio de alertas.
3. Configurar `WHATSAPP_SOLICITUDES_DESTINATARIOS` con números internacionales separados por comas, por ejemplo `+56912345678,+56987654321`. Reiniciar el backend después de cambiar la configuración. Los avisos ya encolados conservan los destinatarios configurados al crear el reporte.
4. Ajustar `WHATSAPP_SOLICITUDES_TEMPLATE_NAME` y `WHATSAPP_SOLICITUDES_TEMPLATE_LANGUAGE` si corresponde y activar `WHATSAPP_SOLICITUDES_ENABLED=true`. El intervalo de sondeo se ajusta con `WHATSAPP_SOLICITUDES_INTERVAL_SECONDS`.
5. Con el backend en ejecución, crear una solicitud autenticada como conductor y revisar el historial de WhatsApp. La aceptación de Meta no confirma entrega ni lectura; no hay webhook de confirmación.

El trabajador necesita una instancia del backend activa con CPU disponible fuera de las peticiones. En plataformas que suspenden la CPU entre solicitudes, se requiere configurar ejecución continua; si no, los avisos pueden quedar pendientes hasta que el proceso vuelva a ejecutarse. El estado se conserva en la base de datos. Las reservas caducadas y los resultados de red inciertos no se reenvían automáticamente para evitar duplicados; los rechazos 429 se reintentan con límite. No hay garantía de entrega exactamente una vez.
