# Especificación de Módulos Narbus Taller

## 1. Módulo Autenticación (`/api/v1/auth`)
- `POST /login`: Autenticación vía payload JSON.
- `POST /login/token`: Autenticación compatible con OAuth2 Password Flow.
- `POST /register`: Registro de nuevos usuarios.
- `GET /me`: Consulta de perfil del usuario logueado.
- `GET /usuarios`: Listado de usuarios (requiere supervisor/admin).
- `POST /usuarios`: Creación administrativa de usuarios.
- `DELETE /usuarios/{id}`: Soft delete (desactivación).

## 2. Módulo Mantención Taller (`/api/v1/mantencion`)
- `GET /categorias`: Catálogo de categorías de falla.
- `GET /fallas`: Maestro de fallas preconcebidas.
- `POST /solicitudes`: Creación de orden de taller.
- `GET /pendientes`: Pestaña 1 mecánico (solicitudes pendientes).
- `GET /mis-trabajos`: Pestaña 2 mecánico (trabajos asignados).
- `GET /{id}`: Obtener detalle completo de solicitud.
- `POST /{id}/tomar`: Auto-asignación como líder + invitar colaboradores.
- `POST /{id}/desasignarme`: Desasignación individual de mecánico.
- `POST /{id}/liberar-turno`: Entrega de turno del equipo completo.
- `PATCH /{id}/detalles/{detalle_id}/check`: Marcar/desmarcar falla resuelta.
- `POST /{id}/comentarios`: Agregar nota a la bitácora.
- `POST /{id}/finalizar`: Cierre de orden y liberación de bus.

## 3. Módulo Neumáticos (`/api/v1/neumaticos`)
- `GET /formularioNeumatico`: Consulta de estado.
- `POST /formularioNeumatico`: Envío de reporte multipart con evidencias.

## 4. Módulo Supervisión (`/api/v1/supervision`)
- `GET /auditoria/buses-taller`: Dashboard auditor de trazabilidad completa.
