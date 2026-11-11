# Sincronización mensual de conductores

Estado al 05-11-2026: sincronización completa aplicada a Neon usando el último
registro de cada RUT en la API. Resultado de esta ejecución: 21 cuentas creadas,
49 actualizadas (15 deshabilitaciones) y 283 sin cambios. Verificación posterior:
353 RUT coincidentes, 128 activos y 225 inactivos, sin faltantes ni diferencias
de estado/datos. Se consolidaron 48 registros repetidos y se omitieron solo 9
registros inactivos sin RUT válido. La misma regla está implementada en el servicio
mensual; su despliegue con el temporizador interno sigue pendiente.

## Sincronización inmediata en Neon

Desde la raíz del repositorio, el script `scripts/incorporar_conductores_neon.py`
actualiza los conductores existentes y crea las cuentas que faltan. No requiere la tabla
`conductor_sync`, no ejecuta migraciones y no consume la ejecución mensual.
Busca cada conductor por RUT: aplica el estado `activo` recibido a `is_active`
y sincroniza sus datos y credenciales. Conserva IDs, teléfonos e historial.
El modo opcional `--solo-nuevos` conserva el comportamiento anterior de solo altas.

Preferentemente configurar `NEON_DATABASE_URL` en el entorno; admite únicamente
la base `taller` en un host `*.neon.tech` y fuerza TLS. No incluye credenciales
en su código ni en el informe. Revisión sin cambios por defecto:

```powershell
.\venv\Scripts\python.exe -m scripts.incorporar_conductores_neon
.\venv\Scripts\python.exe -m scripts.incorporar_conductores_neon --aplicar
```

En este workspace también se puede reutilizar la conexión de mantenimiento
existente, leyendo únicamente el literal mediante AST (sin ejecutar ese script):

```powershell
.\venv\Scripts\python.exe -m scripts.incorporar_conductores_neon --conexion-desde scripts/sanear_estadias_duplicadas.py
.\venv\Scripts\python.exe -m scripts.incorporar_conductores_neon --conexion-desde scripts/sanear_estadias_duplicadas.py --aplicar
```

El informe por defecto se guarda en `.tmp/informe_sincronizacion_conductores_neon.json`;
`--informe RUTA` permite conservar cada ejecución por separado. Incluye cantidades,
fecha UTC, habilitados/inhabilitados y los IDs de los registros de origen
reemplazados u omitidos con su motivo, sin claves ni datos personales.

El padrón real admite apellido nulo; se guarda apellido vacío, conservando el
nombre completo recibido en `nombre`, para compatibilidad con Neon NOT NULL.
Tanto el script como el automático recorren la lista en el orden devuelto por
la API: **el último registro de cada RUT normalizado prevalece**, incluidos su
estado, nombre y apellido. No se omiten RUT repetidos por tener estados distintos.
Esta regla fue elegida explícitamente por el usuario. Los registros inactivos con
RUT inválido se omiten y se identifican en el informe, sin inventar su identidad.
Si un registro activo tiene RUT inválido u otro campo inválido, cancela la carga.
La preparación de datos es compartida entre el script y el servicio mensual.

Las altas y actualizaciones usan una sola transacción y el mismo lock que la
sincronización mensual; si falla la persistencia, se revierte toda la carga.
Una nueva ejecución vuelve a comparar los estados y crea únicamente los RUT
inexistentes. Las credenciales siguen siendo usuario con RUT normalizado y
bcrypt de sus primeros cuatro dígitos.

## Servicio mensual

Estado mensual: implementado y verificable localmente. El timer interno está preparado; requiere desplegar la versión actual. La primera carga urgente del 5 de noviembre de 2026
sí se ejecutó en Neon: 207 cuentas nuevas, 100 existentes conservadas y 103
registros de origen omitidos (9 con RUT inválido y 94 en grupos contradictorios).
La revisión de esa primera carga encontró cero altas pendientes entre los 307 RUT
que procesó. Ese filtro inicial de duplicados quedó reemplazado por la regla del
último registro, tanto para el script como para el automático.

## Comportamiento

- Fuente: `https://backendnarbus-100590754321.us-east4.run.app/api/v1/publico/conductores`.
- Entrada verificada: lista JSON con `rut`, `nombre`, `apellido`, `activo` booleano.
- Usuario: RUT sin puntos, con guion y dígito verificador en mayúscula.
- Contraseña: primeros cuatro dígitos del RUT, almacenados con bcrypt.
  También se restablece esta regla para conductores existentes cada mes.
- Conserva IDs, teléfonos y relaciones históricas. No elimina usuarios.
- Crea conductores nuevos tanto activos como inactivos y actualiza nombre,
  apellido y estado de los existentes. No altera cuentas con otro rol.
- Los conductores ausentes de la respuesta conservan su estado.
- Si hay RUT repetidos en la fuente, prevalece el último registro del API.
  Si hay cuentas locales distintas para el mismo RUT, se cancela la operación
  porque primero debe resolverse la duplicación de cuentas en Neon.
- Una respuesta vacía, inválida o un fallo HTTP no modifica usuarios.

## Programación y autenticación

## Temporizador interno del backend

La sincronización automática se ejecuta dentro de FastAPI, sin Cloud Scheduler
ni GitHub Actions. Se inicia con el lifespan únicamente en `production`, con
`CONDUCTORES_SYNC_TIMER_ENABLED=true` (valor predeterminado).

Comprueba el período cada 60 segundos. Al vencer el día 6 a las 23:59 de
America/Santiago, ejecuta la sincronización mensual. Al arrancar recupera el
último período vencido si no está completado. Los errores se reintentan a los
300 segundos. El apagado cancela la tarea y cierra su sesión de base de datos.
El lock PostgreSQL y el registro mensual existentes evitan duplicados entre
instancias. Los meses ya completados no vuelven a modificar cuentas.

Solo hace falta `CONDUCTORES_SYNC_URL` (ya tiene URL por defecto); no requiere
configurar `CONDUCTORES_SYNC_SECRET` ni un encabezado para el temporizador.
El endpoint HTTP existente queda como alternativa manual opcional: sigue
exigiendo secreto y devuelve 403 si no está configurado. No se abre al público.

Aplicar las migraciones antes de iniciar la nueva versión. Para desactivar el
timer, usar `CONDUCTORES_SYNC_TIMER_ENABLED=false`.

En Cloud Run, el timer no puede despertar un contenedor escalado a cero ni
avanzar mientras no se le asigne CPU. Para ejecutarlo sin depender del tráfico,
configurar al menos una instancia mínima y CPU disponible durante toda la vida
de la instancia (facturación por instancia). Esto puede aumentar el costo del
servicio. Con escalado a cero recupera lo pendiente al volver a arrancar, sin
garantizar ejecución a la hora programada. Las pausas del proceso también
pueden retrasar el timer. No se han cambiado recursos de Google Cloud.

## Reintentos, ejecución manual y auditoría

El servicio toma el último mes cuyo día 6 a las 23:59 ya venció. Por ejemplo,
el 5 de noviembre la ejecución manual corresponde a octubre; el 6 de noviembre
a las 23:59 corresponde a noviembre. No ejecuta meses futuros ni recupera uno
por uno todos los meses anteriores: aplica el snapshot actual al último mes vencido.

Un lock transaccional de PostgreSQL impide concurrencia entre instancias (409 si
ya está en curso). La actualización de usuarios y el registro de `conductor_sync`
se confirman juntos. Tras un error se hace rollback y el job puede reintentar.
Un mes completado responde 200 con `estado=ya_ejecutado` y sus contadores previos.
No vuelve a consultar la fuente ni restablecer claves dentro del mismo mes.

La respuesta y los logs incluyen periodo y cantidades recibidas, creadas,
actualizadas, sin cambios y omitidas por otro rol. Nunca se registran claves.
Se invalida caché y se publican eventos de usuarios tras el commit; las conexiones
locales de cuentas desactivadas se cierran. En otras instancias la caché de
autenticación existente expira en hasta 60 segundos; el backend de tiempo real
actual es en memoria por instancia.

Pruebas aisladas:

```powershell
.\venv\Scripts\python.exe -m pytest tests/unit/test_conductor_sync_service.py tests/integration/test_conductor_sync_api.py -q
```
