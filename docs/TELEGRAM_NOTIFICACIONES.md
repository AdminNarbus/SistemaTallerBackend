# Notificaciones por Telegram

Telegram envía alertas de taller y nuevas solicitudes de conductores. Ambos procesos están desactivados por defecto y se configuran por separado en `.env` con las variables `TELEGRAM_*` documentadas en `.env.example`.

Crear un bot con @BotFather y guardar su token en `TELEGRAM_BOT_TOKEN`. Cada destinatario debe iniciar el bot o agregarlo a un grupo. Obtener los identificadores numéricos de los chats y configurarlos, separados por comas, en `TELEGRAM_DESTINATARIOS` y/o `TELEGRAM_SOLICITUDES_DESTINATARIOS`. No son números de teléfono. Activar únicamente los flujos deseados y reiniciar el backend.

Antes de activar, ejecutar las migraciones de Alembic hasta `045_telegram_linea_base`. El historial es independiente del de WhatsApp. `ACEPTADO` indica que Telegram aceptó la solicitud, no que la persona la leyó. Las solicitudes se despachan después de confirmar la transacción y se recuperan al iniciar el backend. Los rechazos 429 se programan para el momento indicado por Telegram; los resultados de red inciertos no se reenvían automáticamente para reducir duplicados.

Las alertas se evalúan al iniciar, al recibir cambios de OT y en el próximo vencimiento calculado. El programador debe estar ejecutándose para enviar mensajes; al reiniciar recupera el estado actual y los reintentos pendientes. Los cambios efectuados fuera del backend se detectan al reiniciar o al producirse otro evento o vencimiento.

El endpoint manual y la consulta del historial están bajo `/api/v1/supervision/alertas/telegram/envios`. El token concede control del bot y no debe subirse al repositorio ni incluirse en logs.
