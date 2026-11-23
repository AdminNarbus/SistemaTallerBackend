# API de control de mantenciones

Estado: implementación backend local, 10 de noviembre de 2026. Rama `feature/control-mantenciones-odometro`. La página de mantenciones conserva su servidor actual; no está conectada automáticamente a esta API.

## Acceso y ubicación

Base: `/api/v1/control-mantenciones`. Todas las rutas requieren el token Bearer existente del taller y rol SUPERVISOR o ADMIN. No hay usuarios nuevos ni actor fijo de demostración. Los errores usan el contrato central `error.code`, `error.message`, `error.detail`, con mensajes en español.

Los identificadores de bus son los de `buses.id`, no los UUID de la antigua aplicación ni el número de máquina. Se reutiliza el catálogo activo con número; no se importó SQLite.

## Persistencia

Solo tres tablas nuevas: `control_mantenciones`, `control_kilometrajes`, `control_mantenciones_eventos`. La tabla compartida `buses` agrega `intervalo_mantencion_km Numeric(12,2) NULL` con restricción positiva. Los parámetros generales permanecen en `Settings`: `CONTROL_MANTENCIONES_DIAS_RECIENTES=14` y `CONTROL_MANTENCIONES_VENTANA_DIAS=90`.

`NULL` en el intervalo aplica la regla por marca/número: Scania 50.000, Volvo 40.000, Mercedes 354/396 40.000 y otros Mercedes 60.000 km. Marcas no reconocidas devuelven intervalo nulo, sin inventar una regla. Buses y usuarios tienen claves foráneas restrictivas; la eliminación de registros del módulo no elimina entidades compartidas.

No se conservan adjuntos ni bytes del Excel original. Las cargas confirmadas se representan mediante eventos con metadatos, revisión estructurada y relaciones a las lecturas. Los comentarios son eventos vinculados a la mantención. Se preservan estados y valores originales inválidos de las filas para explicarlos; las fechas inválidas se almacenan como NULL operativo y como texto en los datos de origen.

## Endpoints

| Método y ruta relativa | Contrato y función |
|---|---|
| GET `/panel` | Panel paginado con contadores SQL; filtros, búsqueda y ordenamiento |
| GET `/buses/{bus_id}` | Ficha y versión del intervalo |
| PATCH `/buses/{bus_id}/intervalo` | `{version, intervalo_mantencion_km}`; NULL restablece la regla |
| GET `/buses/{bus_id}/grafico` | Serie de seis meses, límite interpolado, divisiones mensuales, escala de 25.000 y vencimiento |
| GET `/buses/{bus_id}/proyeccion` | Estimación o indisponibilidad según las reglas |
| GET `/historial` | Historial combinado, filtrado y paginado |
| GET `/mantenciones` | Historial filtrado a mantenciones |
| POST `/mantenciones` | MantencionCrear; admite datos incompletos |
| GET `/mantenciones/{id}` | Mantención completa para su editor |
| PATCH `/mantenciones/{id}` | MantencionEditar parcial con version; incluye estado y activa |
| DELETE `/mantenciones/{id}` | Cuerpo `{version}`; conserva un evento de eliminación |
| POST `/mantenciones/{id}/comentarios` | `{comentario}`; comentario con autor y fecha |
| GET `/kilometrajes` | Historial filtrado a lecturas |
| POST `/kilometrajes` | `{bus_id, fecha, kilometraje}`; corrección adicional sin reemplazar el original |
| GET `/kilometrajes/{id}` | Lectura completa para revisión |
| PATCH `/kilometrajes/{id}` | `{version, fecha? , kilometraje?}`; solo lecturas no aceptadas |
| POST `/kilometrajes/{id}/decisiones` | `{version, accion: aceptar o excluir}` |
| POST `/importaciones/previsualizacion` | Multipart `files`; devuelve borradores sin persistencia |
| POST `/importaciones/validaciones` | Borrador completo corregido; reevalúa sin persistencia |
| POST `/importaciones` | Confirma un borrador, devuelve carga_id, resumen y buses_afectados |
| GET `/importaciones` | Lista paginada de cargas confirmadas, sin incluir todas sus filas |
| GET `/importaciones/{id}` | Metadatos de carga, sin descargar el archivo original |
| GET `/importaciones/{id}/filas` | Resultados de filas, paginados y filtrables por estado |
| DELETE `/importaciones/{id}?confirmar=true` | Retira carga, sus kilometrajes y eventos asociados |
| GET `/eventos` | Auditoría y comentarios; permite bus_id y mantencion_id |
| GET `/exportaciones` | Excel filtrado; area=panel, historial, eventos o cargas |

Listados: `skip>=0`, `1<=limit<=100`, valor predeterminado 50. Respuesta: `{items,total,skip,limit}`; el panel agrega `contadores`. Historial desplegable recomendado: limit=10; auditoría: limit=50. Filtros comunes: bus_id, buscar, desde, hasta, estado, tipo=todos/mantencion/kilometraje y ordenar=bus/restantes/fecha. Los decimales deben tratarse como cantidades exactas y enviarse preferentemente como cadenas sin separadores de miles. Las fechas operativas usan YYYY-MM-DD. Recursos individuales usan `{datos: ...}`. Consulte OpenAPI para DTOs y límites de campos.

## Flujo del Excel y borrador del navegador

1. Enviar hasta diez `.xlsx`, de hasta 20 MB cada uno, con hoja exacta `Query result` y encabezados únicos `n_bus`, `fecha`, `odometro`. Se admiten columnas adicionales; la hora se ignora. El parser valida el ZIP y limita contenido expandido a 200 MB, filas a 100.000 y columnas a 500. Procesamiento y generación de Excel se ejecutan fuera del event loop.
2. Guardar en IndexedDB del navegador el objeto `borrador` recibido, incluyendo clave_operacion y los UUID de las filas. Previsualizar y validar no crean eventos, lecturas ni cargas en PostgreSQL.
3. Para corregir una celda, actualizar solo fecha o kilometraje de esa fila y enviar el borrador a `/importaciones/validaciones`. Sustituir los resultados visibles por la respuesta y cerrar el editor en el cliente. El cliente puede conservar los valores previos para mostrar su indicador Editada.
4. Los resultados incluyen lectura actual, anterior guardada, motivos y selección del registro más reciente. Una fecha inválida utiliza el último registro válido del historial para comparación. Si hay varias filas del bus, se elige la fecha válida más reciente y se detectan valores distintos en la misma fecha. Las filas antiguas no generan nuevas lecturas.
5. En filas pendientes se puede elegir pendiente, aceptar o excluir mediante `fila.decision`. Aceptar requiere bus identificado, fecha no futura y kilometraje válido. Una incongruencia de secuencia puede resolverse por decisión explícita; un error estructural debe corregirse antes.
6. Al pulsar Confirmar registro, enviar el borrador a POST `/importaciones`. La revisión se repite bajo bloqueos por bus y se guarda en una transacción. Reintentar el mismo UUID y contenido devuelve el resultado previo; cambiar contenido con la misma clave produce 409. Distintas cargas del mismo bus se serializan y una lectura repetida queda excluida del cálculo, con motivo de duplicado.
7. Solo tras recibir éxito, retirar el borrador local, recargar el panel y navegar a él en el futuro frontend. Si falla la petición, conservar el borrador para corregir o reintentar.

Ejemplo de borrador (los UUID deben conservarse al editar/reintentar):

```json
{
  "clave_operacion": "01f95024-783c-4c64-9ac3-48e38d6fd0f1",
  "nombre_archivo": "semana.xlsx",
  "filas": [{"id":"c28ec6bb-63fb-4976-9eec-e9b7603d40fe","fila":2,"numero_bus":"354","fecha":"2026-11-06","kilometraje":"1422000","decision":"pendiente"}]
}
```

## Reglas de cálculo y edición

- Solo lecturas aceptadas y mantenciones activas con fecha y kilometraje participan en los cálculos. Registros incompletos y pendientes siguen consultables.
- Próxima mantención vigente: última mantención válida + intervalo efectivo. Cada fila histórica de mantención calcula su propia próxima mantención con su kilometraje y el intervalo vigente; no existe un snapshot histórico del intervalo.
- Restantes <=0: Vencida; <=5.000: Crítica; <=25.000: Próxima; resto: Al día. La antigüedad de lectura y los conflictos son estados adicionales.
- Un pendiente relevante o un empate de valores distintos bloquea el kilometraje operativo; la ficha conserva visible el último confirmado cuando existe. La edición no aceptada reevalúa estado, sin exigir una segunda confirmación de carga.
- Proyección: 90 días, al menos tres fechas distintas, siete días de cobertura, secuencia creciente, promedio positivo y ausencia de conflictos. El redondeo de días se hace hacia arriba. Una mantención sin fecha o kilometraje no participa aunque su estado sea completa.
- El punto interpolado en el inicio del gráfico tiene id nulo e interpolado=true: el cliente no debe tratarlo como registro real editable. Los valores se entregan como Decimal cuantizado, sin concatenaciones numéricas.
- Ediciones usan version. Una versión desactualizada retorna 409. El intervalo usa version_intervalo de la ficha (0 si nunca se cambió), que corresponde al último evento de modificación.
- Tras registrar un bus previamente desconocido en el catálogo compartido, editar o decidir su lectura resuelve nuevamente su identidad por número.
- Eliminar una carga borra sus lecturas y eventos de edición/decisión, sin tocar registros de otras cargas. Los indicadores y gráficos consultan las fuentes vigentes y recuperan el anterior. Deshabilitar mantención usa PATCH activa=false; eliminarla conserva su evento de eliminación y la bitácora disponible por bus.

## Migraciones, validación y limitaciones conocidas

037_unificar_cabeceras une las cabeceras previas del repositorio; 038_control_mantenciones agrega exclusivamente las tres tablas y la columna acordadas. Se comprobó upgrade, downgrade -1 y upgrade en PostgreSQL temporal. Se aplicaron en dev_local con respaldo previo verificado mediante pg_restore --list. El upgrade local incluyó también las revisiones pendientes existentes 035_comentarios_neumaticos y 036_estado_neumaticos. No se sembraron registros del módulo.

La comparación Alembic específica del módulo pasa. El comando global `alembic check` sigue señalando diferencias previas ajenas: tabla taller_correcciones_visitas sin migración, representación del índice de ciudades y nombre de restricción única en taller_resultado_ubicaciones. Se documentan sin incorporarlas a esta entrega.

Pruebas: `python -m pytest tests/control_mantenciones -q`. Regresión ampliada: agregar tests/unit/test_bus_service.py, tests/integration/test_buses_api.py, tests/integration/test_buses_mecanicos_api.py y tests/dashboard. Las pruebas nuevas levantan un clúster PostgreSQL temporal y lo eliminan al terminar; no utilizan la base operativa para escritura.

## Matriz de adopción

| Funcionalidad de la página | API / prueba |
|---|---|
| Panel, búsqueda y estados | panel; test_flujo_confirmacion_borrado_y_panel |
| Intervalo y mantención histórica | intervalo + historial; test_mantenciones_intervalos_comentarios_y_concurrencia |
| Edición y estado de lectura | kilometrajes PATCH; test_edicion_reevalua_fecha_y_kilometraje |
| Comentarios y estados de mantención | mantenciones PATCH/comentarios + eventos; pruebas API y PostgreSQL |
| Revisar sin guardar | previsualizacion + validaciones; test_api_excel_no_guarda_y_confirmacion |
| Confirmar sin duplicar | importaciones POST; test_confirmacion_concurrente_y_rollback |
| Errores y filas por página | importaciones/{id}/filas; test_resultados_errores_y_paginacion |
| Gráfico y proyección | grafico + proyeccion; test_proyeccion_y_limite_del_grafico |
| Borrar carga y recuperar anterior | importaciones DELETE; test_flujo_confirmacion_borrado_y_panel |
| Exportación | exportaciones; pruebas API y apertura real del Excel |
| Acceso por rol | dependencia existente; test_api_permisos_contratos_y_exportacion |
| Tablas y reversión | test_schema y fixture PostgreSQL con ciclo Alembic |
