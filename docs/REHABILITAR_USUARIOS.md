# Reactivar usuarios

`PATCH /api/v1/auth/usuarios/{usuario_id}/habilitar`

Requiere Bearer token de SUPERVISOR o ADMIN. No requiere body.
Responde 200 con UsuarioResponseDTO e is_active=true; conserva datos, rol y contraseña.
Repetir sobre un usuario activo también devuelve 200.
Errores: 401 sin sesión válida, 403 sin permisos, 404 usuario inexistente.

Listar inactivos: `GET /api/v1/auth/usuarios?is_active=false`.
Mostrar Habilitar y actualizar la fila o recargar el listado después del PATCH.
Evento realtime: resource.changed, resource_type=user, action=activated.
No requiere migraciones; reutiliza usuarios.is_active.
