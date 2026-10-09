# Corregir visitas creadas automáticamente al reportar una OT

Este corrector de PostgreSQL usa la conexión configurada en `.env` / `DATABASE_URL`.
Por defecto rechaza destinos fuera de localhost antes de conectarse.

Desde la raíz del backend, revisar las OT confirmadas en las capturas:

```powershell
.\venv\Scripts\python.exe -m scripts.fix_visitas_falsas_ot --ot 3:377 --ot 43:391
```

Aplicarlas en la base local:

```powershell
.\venv\Scripts\python.exe -m scripts.fix_visitas_falsas_ot --ot 3:377 --ot 43:391 --aplicar
```

El script prepara su propia tabla de originales al aplicar la corrección, sin
añadir migraciones a Alembic. El modelo de esa tabla se registra también en el
backend para que Alembic reconozca el archivo existente.

Cada `--ot` confirma que esa OT y ese bus nunca ingresaron físicamente al taller.
Si los IDs locales son diferentes, utilizar los IDs y buses correspondientes.
Sin `--ot` y sin `--aplicar`, lista candidatos para revisión; la coincidencia del
patrón por sí sola no demuestra que una visita sea falsa. No aplica correcciones masivas.

Para aceptar una OT exige: estado PENDIENTE/REPORTADO, exactamente una visita
abierta #1 con ingreso igual a la creación, primer ingreso igual a creación y demora
cero. Rechaza órdenes con comentarios, mecánicos, asignaciones, respuestas de pauta,
transiciones de estado, fallas atendidas o eventos de trabajo. Una OT pendiente con
ingreso físico real puede tener ese mismo patrón: seleccionar únicamente casos confirmados.

Archiva la visita y los datos originales de OT y bus en
`taller_correcciones_visitas`, retira la visita espuria, deja primer ingreso y demora
en NULL, pone horas acumuladas en cero y recalcula `buses.en_taller` desde las visitas
abiertas restantes. Conserva el estado, la fecha de creación y las averías reportadas.
Los originales quedan disponibles en la tabla de archivo para una recuperación controlada.

Todo se ejecuta en una transacción. Bloquea escrituras durante la corrección y
suspende únicamente el trigger que impide borrar estadías, restaurándolo antes de
confirmar. Ante cualquier error revierte los cambios, incluido el estado del trigger.
Una segunda ejecución omite las OT ya archivadas y conserva ingresos reales posteriores.

## Uso posterior en producción

Desplegar también el cambio del backend que elimina el ingreso automático por rol.
Configurar la conexión de producción en el entorno del proceso que lo ejecutará,
revisar los mismos comandos añadiendo `--permitir-remoto` y luego utilizar
`--aplicar` para la corrección. El archivo no contiene credenciales ni consulta
producción durante su preparación local.

La corrección no es una migración automática de arranque: su selección explícita
evita modificar por error otras visitas pendientes que sí fueron reales.
