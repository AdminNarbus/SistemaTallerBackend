# Permanencia física en taller

`GET /api/v1/supervision/auditoria/buses-taller` devuelve `tiempo_taller`,
`horas_en_taller` y `horas_taller_acumuladas` con la misma permanencia física,
en horas con un decimal. La antigüedad desde creación no interviene.

Se suman las estadías, priorizando `horas_estadia` y usando las fechas cuando
no hay duración guardada. Las visitas abiertas corren solamente en reparación;
en LIBERADO/FINALIZADO se congelan en liberación/cierre, respectivamente.
Sin estadías se usa el acumulado positivo y luego el primer ingreso físico.
Sin fecha de salida ni estado activo no se proyectan horas hasta hoy.
PENDIENTE sin ingresos registra cero.

`GET /api/v1/buses/{id}` y la consulta de ficha por número incluyen
`horas_taller_totales`: suma SQL de todas las OTs del bus, sin paginación,
sin incluir solicitudes no convertidas a OT y sin consultas por cada orden.
Bus sin OTs devuelve cero. Las otras respuestas del DTO de bus dejan este
campo en null cuando no se calcula. No requiere migración de base de datos.
