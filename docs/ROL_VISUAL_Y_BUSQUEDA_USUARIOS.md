# Rol VISUAL y búsqueda de usuarios

## Búsqueda

Los listados `GET /api/v1/auth/usuarios`, `GET /api/v1/supervision/usuarios`
y el autocompletado `GET /api/v1/auth/mecanicos` (también `/mecanicos/buscar`)
aceptan el parámetro `q` separado por palabras. Todas deben coincidir en el
nombre, apellido o username, sin importar el orden ni mayúsculas/minúsculas.

Ejemplo: `q=Juan Perez` encuentra a `Juan Carlos Perez Soto`.
También acepta `q=Perez Juan` y espacios repetidos. Los filtros por rol,
estado y paginación se conservan; `X-Total-Count` usa el mismo criterio.
Los caracteres `%` y `_` se interpretan literalmente, no como comodines SQL.
Esta búsqueda no elimina diferencias de tildes.

## Rol de consulta

El identificador del rol es `VISUAL`. Admin o supervisor pueden crear una
cuenta con `POST /api/v1/auth/usuarios`, enviando por ejemplo:

```json
{"username": "consulta", "password": "1234", "rol": "VISUAL"}
```

El registro público sigue creando únicamente conductores. El perfil de login,
refresh y `/auth/me` devuelve `rol: "VISUAL"`.

VISUAL puede consultar las rutas GET protegidas de usuarios, supervisión,
taller y dashboard. Conserva los filtros propios de cada consulta (por ejemplo,
`mis-trabajos` continúa filtrando por la cuenta autenticada). También puede
recibir actualizaciones por el WebSocket de tiempo real, que solo procesa
autenticación y ping.

Las operaciones de escritura autenticadas como VISUAL devuelven HTTP 403,
incluidos formularios con autenticación opcional y sus alias. Se exceptúan
login JSON, login OAuth2 y refresh, necesarios para gestionar la sesión.
La protección común se aplica al router completo `/api/v1`; las dependencias
por rol también rechazan escrituras de VISUAL.

El frontend debe incorporar VISUAL al selector de roles y usar el rol del
perfil para ocultar o deshabilitar botones y formularios de creación, edición,
eliminación, asignación y carga de archivos. El backend aplica los permisos
aunque el cliente intente enviar las peticiones directamente.

## Migración

La revisión `040_rol_visual`, posterior a `039_conductor_sync`, incorpora el
rol en la tabla `roles` sin duplicarlo si ya existe. Aplicar mediante el
procedimiento habitual `alembic upgrade head` antes de desplegar.
El downgrade elimina el rol y la FK impide hacerlo si existen usuarios
asignados: hay que resolver esas cuentas antes de revertir.

Las pruebas de migración ejecutan upgrade, repetición idempotente, downgrade
y nuevo upgrade sobre una base temporal; no modifican producción.
