# Integridad de la BD del taller

## Decisiones de dominio

- La pauta de trabajo es únicamente el catálogo activo actual de diez ítems. No hay versiones de pauta por OT. Los registros anteriores se conservan como historial, sin ofrecerlos para nuevas respuestas.
- Cada nuevo reporte de neumáticos contiene exactamente un neumático. `ruedas` se almacena como una lista JSON de un elemento para conservar el contrato del formulario; admite una posición simple o un objeto. `marca_fuego` es opcional y pertenece a ese neumático.
- `empresa_id` es un identificador externo, sin tabla de empresas ni clave foránea.
- Catálogos, usuarios y buses se desactivan; sus referencias operacionales no se eliminan mediante cascadas.
- `estado` es la definición del avance de una falla. Se conserva `resuelto` por compatibilidad, con una restricción que exige que corresponda a `estado='RESUELTA'`.
- `n_bus` de la OT es su identificador histórico; al crearla con `bus_id` se comprueba que ambos correspondan. Los buses sin número de máquina pueden existir como fichas de flota, identificadas por su patente.
- Los nombres de falla y categoría se capturan al insertar el detalle y no cambian al renombrar el catálogo. El backfill representa los nombres disponibles al migrar; no pretende reconstruir nombres antiguos que no fueron registrados.
- Las estadías son la fuente para la telemetría. PostgreSQL calcula sus horas, reconcilia el acumulado de la OT y sincroniza `bus.en_taller`. Los movimientos físicos por la API abren o cierran la estadía cuando existe una OT activa; se permiten movimientos sin OT.
- Las fechas nuevas usan UTC con zona horaria. Las correcciones confirmadas se expresan explícitamente en hora de Chile.

## Migraciones nuevas

1. `021a_saneamiento_historial`: saneamiento confirmado por el operador. Cierra las estadías de la OT 3, separa el reporte 1 preservando su payload original y normaliza reportes individuales guardados como escalares u objetos. Las correcciones específicas exigen ID, datos originales y fechas de ingreso exactos para evitar modificar filas distintas en otro entorno.
2. `022_integridad_bd`: validación SELECT previa, checks de estados y fechas, índices únicos de asignaciones/estadías/identidades, FK compuestas para asegurar pertenencia a la misma OT, protección de relaciones históricas, snapshots de catálogo, alineación de defaults e índices con los modelos y eliminación de índices redundantes de PK. No importa modelos actuales: sus definiciones están congeladas en el archivo.
3. `023_auditoria_inmutable`: triggers que impiden UPDATE/DELETE de comentarios, eventos y participantes; protegen snapshots, impiden borrar estadías y calculan telemetría a partir de sus fechas.

La unicidad de asignaciones activas es por mecánico y falla/OT; permite a varios mecánicos colaborar y conserva turnos anteriores. Solo puede existir una estadía abierta por OT y un número de visita por OT. La restricción existente de una OT activa por bus sigue vigente.

## Correcciones confirmadas

Hora America/Santiago, UTC-03:00:

| Estadía | OT | Fecha de salida |
|---|---|---|
| 1, visita 1 | 3 | 2026-09-29 13:00 |
| 3, visita 3 | 3 | 2026-10-02 14:00 |
| 4, visita 4 | 3 | 2026-10-02 15:00 |

El reporte 1 tenía posiciones 1D/1I y marca `MF-301-A`. El operador confirmó que la marca corresponde a 1D: se conserva en el reporte original y se crea un reporte de 1I sin marca. El nuevo registro conserva una referencia al reporte de origen. El precio histórico permanece en el original y no se duplica.

## Compatibilidad y limpieza

- El precio se retira del uso operativo del modelo y servicio, pero la columna SQL `precio` permanece como `precio_historico` en el ORM. Esto conserva importes y compatibilidad con un despliegue anterior.
- `foto_url` permanece como portada compatible con la API existente; las evidencias son el conjunto de adjuntos. Su eliminación física necesita una transición del contrato y no se hace destruyendo referencias existentes.
- Los campos de ficha importada (`astos`, `anio`, `tipo`, `clasificacion`, `min`, `max`) se conservan. No se reinterpretan ni eliminan campos externos sin una definición de negocio. Las magnitudes numéricas cuentan con controles de no negatividad y rango cuando corresponde.
- El seed de pauta ya no elimina respuestas cuyo `item_id` sea mayor que diez: los IDs no representan el orden ni la cantidad de ítems. Se consultan y sincronizan únicamente ítems activos.
- Se conserva la representación JSON de `ruedas`; no se añade inventario ni historial de montajes de neumáticos porque no pertenecen al alcance confirmado.

## Verificación y despliegue

Las migraciones se validaron en PostgreSQL local desechable con una copia SELECT de los datos del proyecto. La copia de pruebas se elimina al finalizar. Se probó upgrade, `alembic check`, downgrade hasta 021 y nuevo upgrade/check, además de rechazos reales de FK, duplicados y modificaciones de bitácora.

Herramientas:

```powershell
python -m scripts.validar_migraciones_postgres
python -m scripts.verificar_integridad_bd
```

`validar_migraciones_postgres` solo admite localhost y utiliza una BD temporal con prefijo `narbus_bd_test_`. Nunca migra la BD fuente. `verificar_integridad_bd` abre una transacción READ ONLY y devuelve código 1 cuando encuentra inconsistencias.

Para producción: respaldar la BD con su mecanismo habitual y desplegar el código junto con la cadena completa de migraciones. Usar el proceso Alembic existente (`alembic upgrade head`) y luego `alembic check`. No ejecutar el script de aplicación local contra producción. El preflight de 022 puede bloquear el despliegue si ese entorno tiene datos históricos distintos e incompatibles; deben corregirse mediante otra migración revisada, sin desactivar las restricciones.

Los cambios son transaccionales en PostgreSQL, con espera de locks limitada a cinco segundos. Crear índices puede bloquear escrituras mientras dura la transacción: programar el despliegue según el volumen real. No es una migración concurrente para tablas de gran volumen.

El downgrade restaura el esquema anterior y las representaciones históricas saneadas cuando siguen identificables. Retira columnas de snapshots y protecciones; no es un procedimiento de restauración de los cambios de negocio realizados después del despliegue. Conservar el respaldo para ese caso y evitar downgrade con tráfico de escritura.

La instancia local fue respaldada bajo `backups/` y actualizada exclusivamente con Alembic hasta `023_auditoria_inmutable`. Producción no fue modificada.


## Validación con datos reales de Neon (6 de octubre de 2026)

Origen: BD `taller` de Neon, revisión `018_estado_falla_detalles`. Se capturaron 16 tablas y 666 registros en una transacción REPEATABLE READ READ ONLY. El respaldo final está en `backups/neon_taller_20261006T194641Z.json`. Es un respaldo de datos; la estructura se reconstruyó con las migraciones Alembic y se comprobó mediante `alembic check`. El pg_dump 16 instalado no soporta el servidor Neon 17; no se presenta ese intento como un respaldo completo nativo.

La restauración de este mismo JSON fue comprobada en `narbus_bd_test_neon_6b1c8b4ac2` (localhost). Neon recibió únicamente consultas de lectura. No se realizó despliegue ni aplicación de migraciones en Neon.

Se encontró que 021 reúne las OTs 16 y 19 del bus 402 y sus estadías abiertas. 020a captura íntegramente las OTs y todos sus registros hijos antes de consolidar, incluidas las respuestas de pauta que 021 descarta de la vista operativa. 021b conserva una sola estadía operativa abierta, la de ingreso más antiguo, y mantiene la otra íntegra en el archivo, con su OT original. Es una consolidación administrativa: no se inventan salidas ni duración de permanencias. Solo se aplica si todas las estadías abiertas están archivadas y proceden de OTs originales distintas. Las duplicidades dentro de una misma OT siguen bloqueando 022.

025 crea el archivo también para entornos ya en 024 (sin inventar originales de consolidaciones previas), y prohíbe UPDATE, DELETE y TRUNCATE. Se incorporaron 020a antes de 021 y 021b antes de 022: solo se cambian los enlaces down_revision de esas revisiones; su SQL de negocio permanece intacto. El head es ahora `025_proteger_archivo`.

Pasaron: restauración y conteos de cada tabla; upgrade 018→025; verificación de cada campo archivado contra el respaldo; comprobación de que cada ID original sigue operativo o archivado; auditoría de integridad; restricciones PostgreSQL; historial, concurrencia y rollback de servicios; downgrade a 021 y reaplicación hasta 025; alembic check en ambos upgrades. Revertir por debajo de 020a con archivos existentes aborta para no borrar el historial preservado. Downgrade es una reversión técnica del esquema, no una restauración automática de OTs ya consolidadas.

Comando reproducible: `python -m scripts.validar_copia_neon`. El destino debe ser localhost y la copia se conserva. Para producción, usar una ventana de mantenimiento y respaldo/snapshot recuperable del proveedor; estas pruebas validan los datos capturados, no eliminan los riesgos de bloqueos ni cambios posteriores en el origen.
