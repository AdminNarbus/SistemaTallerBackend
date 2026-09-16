# Catálogo Exhaustivo de Endpoints, Payloads y Respuestas: Backend Taller Narbus

> **Documento Oficial de Especificación de Interfaz REST API**  
> **Versión:** 2.2.0  
> **Fecha de Actualización:** 2026-09-15  
> **Proyecto:** Backend Taller Narbus (`FastAPI + SQLAlchemy Async + PostgreSQL`)  
> **Base URL:** `http://localhost:8000/api/v1` (o `/api/v1` en producción)  
> **Total de Endpoints:** 48 endpoints activos

---

## Tabla de Contenidos

1. [Convenciones Generales y Manejo de Errores](#1-convenciones-generales-y-manejo-de-errores)
2. [Módulo 0: Root y Verificación de Estado (Health)](#2-módulo-0-root-y-verificación-de-estado-health)
3. [Módulo 1: Autenticación y Gestión de Usuarios (`/auth`)](#3-módulo-1-autenticación-y-gestión-de-usuarios-auth)
4. [Módulo 2: Catálogo de Buses y Flota de Taller (`/buses`)](#4-módulo-2-catálogo-de-buses-y-flota-de-taller-buses)
5. [Módulo 3: Formulario Operativo de Neumáticos (`/formularioNeumatico`)](#5-módulo-3-formulario-operativo-de-neumáticos-formularioneumatico)
6. [Módulo 4: Mantención de Taller y Pauta Preventiva (`/mantencion`)](#6-módulo-4-mantención-de-taller-y-pauta-preventiva-mantencion)
7. [Módulo 5: Supervisión, KPIs y Auditoría de Taller (`/supervision`)](#7-módulo-5-supervisión-kpis-y-auditoría-de-taller-supervision)

---

## 1. Convenciones Generales y Manejo de Errores

### 1.1 Autenticación
Los endpoints protegidos requieren el envío del Token JWT Bearer en la cabecera HTTP:
```http
Authorization: Bearer <access_token>
```

Los roles admitidos en el sistema son:
- `CONDUCTOR`: Chofer o conductor que reporta averías de buses.
- `MECANICO`: Mecánico o técnico de taller que repara, realiza pautas y entrega turnos.
- `SUPERVISOR`: Jefa o supervisor de taller encargado de asignaciones, auditoría y alertas.
- `ADMIN`: Administrador con privilegios globales.

### 1.2 Formato Unificado de Errores
El backend implementa un manejador centralizado de excepciones (`NarbusException`). Todas las respuestas de error siguen el esquema:

```json
{
  "error": {
    "code": "BUSINESS_RULE_VIOLATION",
    "message": "Descripción comprensible del error de negocio",
    "detail": null
  }
}
```

Códigos de error estándar:
- `BUSINESS_RULE_VIOLATION` (`422 Unprocessable Content`): Regla de negocio infringida (ej: intentar liberar bus con pauta incompleta sin justificación).
- `NOT_FOUND` (`404 Not Found`): Recurso solicitado inexistente en base de datos.
- `CONFLICT` (`409 Conflict`): Conflicto de estado o duplicidad de clave única.
- `FORBIDDEN` (`403 Forbidden`): Usuario autenticado sin el rol necesario para la operación.
- `HTTP_ERROR` (`401 Unauthorized`): Token ausente, inválido o expirado.
- `VALIDATION_ERROR` (`422 Unprocessable Content`): Falla de esquema o tipo en el payload de Pydantic.

---

## 2. Módulo 0: Root y Verificación de Estado (Health)

### 2.1 `GET /`
- **Autenticación:** Pública.
- **Propósito:** Endpoint de bienvenida e inspección rápida del backend y documentación activa.
- **Parámetros:** Ninguno.
- **Payload:** Ninguno.
- **Respuesta (200 OK):**
```json
{
  "message": "Welcome to Narbus Taller API",
  "environment": "dev_local",
  "docs": "/docs",
  "health": "/api/v1/health"
}
```

---

### 2.2 `GET /api/v1/health`
- **Autenticación:** Pública.
- **Propósito:** Verificación de liveness del servicio API (usado por balanceadores de carga y monitoreo de contenedores).
- **Parámetros:** Ninguno.
- **Payload:** Ninguno.
- **Respuesta (200 OK):**
```json
{
  "status": "ok",
  "service": "Backend Taller Narbus"
}
```

---

### 2.3 `GET /api/v1/health/db`
- **Autenticación:** Pública.
- **Propósito:** Verificación de conectividad activa (readiness) con el motor de base de datos PostgreSQL mediante ejecución de `SELECT 1`.
- **Parámetros:** Ninguno.
- **Payload:** Ninguno.
- **Respuesta Exitosa (200 OK):**
```json
{
  "status": "healthy",
  "database": "connected"
}
```
- **Respuesta Fallida (503 Service Unavailable):**
```json
{
  "status": "unhealthy",
  "database": "disconnected",
  "detail": "Error de conexión con la base de datos."
}
```

---

## 3. Módulo 1: Autenticación y Gestión de Usuarios (`/auth`)

### 3.1 `POST /api/v1/auth/login`
- **Autenticación:** Pública.
- **Propósito:** Inicio de sesión para clientes web/móvil mediante JSON. Emite el token JWT Bearer e incluye el perfil del usuario.
- **Parámetros:** Ninguno.
- **Payload (`UsuarioLoginDTO` - `application/json`):**
```json
{
  "username": "mecanico_juan",
  "password": "PasswordSegura123!"
}
```
  - **Explicación de campos del Payload:**
    - `username` *(string, obligatorio)*: Nombre de usuario o identificador de acceso de la cuenta.
    - `password` *(string, obligatorio)*: Contraseña en texto plano para verificación hash criptográfica.
- **Respuesta (`TokenDTO` - 200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 5,
    "nombre": "Juan",
    "apellido": "Pérez",
    "nombre_completo": "Juan Pérez",
    "rut": "15.345.678-9",
    "username": "mecanico_juan",
    "rol": "MECANICO",
    "is_active": true
  }
}
```

---

### 3.2 `POST /api/v1/auth/login/token`
- **Autenticación:** Pública.
- **Propósito:** Autenticación compatible con OAuth2 Password Flow (`application/x-www-form-urlencoded`), utilizado por la interfaz Swagger `/docs`.
- **Payload (`OAuth2PasswordRequestForm` - Form Data):**
  - `username` *(string, obligatorio)*: Nombre de usuario.
  - `password` *(string, obligatorio)*: Contraseña.
  - `grant_type` *(string, opcional, default: "password")*: Tipo de concesión OAuth2.
- **Respuesta (`TokenDTO` - 200 OK):** Mismo objeto que en `/login`.

---

### 3.3 `POST /api/v1/auth/register`
- **Autenticación:** Pública.
- **Propósito:** Registro libre de nuevos usuarios (choferes/mecánicos). Crea la cuenta y retorna sesión iniciada con JWT.
- **Payload (`UsuarioCreateDTO` - `application/json`):**
```json
{
  "nombre": "Mario",
  "apellido": "Gómez",
  "username": "mgomez",
  "password": "Password123!",
  "rol": "CONDUCTOR",
  "is_active": true
}
```
  - **Explicación de campos del Payload:**
    - `nombre` *(string, opcional)*: Primer nombre del usuario.
    - `apellido` *(string, opcional)*: Apellido del usuario.
    - `username` *(string, obligatorio, longitud 3 a 100)*: Nombre de usuario único en el sistema.
    - `password` *(string, obligatorio, longitud mín 6)*: Contraseña que será hasheada en BD.
    - `rol` *(string, opcional, default: "CONDUCTOR")*: Rol operativo asignado (`CONDUCTOR`, `MECANICO`, `SUPERVISOR`, `ADMIN`).
    - `is_active` *(boolean, opcional, default: true)*: Indica si la cuenta se crea activa de inmediato.
- **Respuesta (`TokenDTO` - 201 Created):** Token JWT y datos del usuario creado.

---

### 3.4 `GET /api/v1/auth/me`
- **Autenticación:** Token Bearer (`require_current_user`).
- **Propósito:** Retorna el perfil y rol del usuario autenticado que realiza la solicitud.
- **Parámetros / Payload:** Ninguno.
- **Respuesta (`UsuarioResponseDTO` - 200 OK):**
```json
{
  "id": 5,
  "nombre": "Juan",
  "apellido": "Pérez",
  "nombre_completo": "Juan Pérez",
  "rut": "15.345.678-9",
  "username": "mecanico_juan",
  "rol": "MECANICO",
  "is_active": true
}
```

---

### 3.5 `GET /api/v1/auth/mecanicos/buscar` y `GET /api/v1/auth/mecanicos`
- **Autenticación:** Token Bearer (`require_current_user`).
- **Propósito:** Buscador y autocompletado de mecánicos activos para asignación de tareas, co-responsabilidad y entrega de turnos.
- **Parámetros Query:**
  - `q` *(string, opcional, default: "")*: Texto de búsqueda por nombre, apellido o username. Si se envía vacío, retorna todos los mecánicos activos.
  - `exclude_id` *(integer, opcional)*: ID de usuario a excluir de la lista (útil para que el mecánico que busca colaboradores no se vea a sí mismo).
- **Payload:** Ninguno.
- **Respuesta (`List[UsuarioResponseDTO]` - 200 OK):** Lista de mecánicos activos disponibles.

---

### 3.6 `GET /api/v1/auth/usuarios`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Listado administrativo de todos los usuarios registrados en el sistema con soporte de paginación.
- **Parámetros Query:**
  - `skip` *(integer, opcional, default: 0, ge: 0)*: Desplazamiento/offset de registros.
  - `limit` *(integer, opcional, default: 100, ge: 1, le: 500)*: Cantidad máxima de usuarios a retornar.
- **Payload:** Ninguno.
- **Respuesta (`List[UsuarioResponseDTO]` - 200 OK):** Lista de usuarios.

---

### 3.7 `POST /api/v1/auth/usuarios`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Creación directa de usuarios por parte de un supervisor o administrador desde el panel de control.
- **Payload (`UsuarioCreateDTO` - `application/json`):**
  - Mismos campos que en `POST /auth/register`.
- **Respuesta (`UsuarioResponseDTO` - 201 Created):**
```json
{
  "id": 8,
  "nombre": "Roberto",
  "apellido": "Díaz",
  "nombre_completo": "Roberto Díaz",
  "rut": null,
  "username": "rdiaz",
  "rol": "MECANICO",
  "is_active": true
}
```

---

### 3.8 `DELETE /api/v1/auth/usuarios/{usuario_id}`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Desactivación lógica (Soft Delete) de un usuario (`is_active = False`). No elimina físicamente la fila para preservar la trazabilidad de auditoría histórica de reparaciones.
- **Parámetros Path:**
  - `usuario_id` *(integer, obligatorio)*: ID del usuario a deshabilitar.
- **Payload:** Ninguno.
- **Respuesta (`UsuarioResponseDTO` - 200 OK):** Usuario actualizado con `is_active: false`.
- **Restricción:** No es posible deshabilitar la propia cuenta en sesión (retorna `400 Bad Request`).

---

## 4. Módulo 2: Catálogo de Buses y Flota de Taller (`/buses`)

### 4.1 `GET /api/v1/buses/buscar`
- **Autenticación:** Pública.
- **Propósito:** Autocompletado ágil de números de máquinas para cajas de texto en formularios de reporte. Devuelve un arreglo plano de strings con números de máquinas coincidentes.
- **Parámetros Query:**
  - `query` *(string, opcional)*: Prefijo numérico (ej: `"30"`).
  - `solo_flota_taller` *(boolean, opcional, default: true)*: Si es `true`, filtra los buses operativos del taller (eliminada la restricción estática numérica 200..900 para abarcar la flota completa).
- **Payload:** Ninguno.
- **Respuesta (`List[str]` - 200 OK):**
```json
["301", "302", "305", "309"]
```

---

### 4.2 `GET /api/v1/buses`
- **Autenticación:** Pública.
- **Propósito:** Catálogo general de buses con atributos básicos y flag de presencia física en taller.
- **Parámetros Query:**
  - `solo_activos` *(boolean, opcional, default: true)*: Excluye buses dados de baja.
  - `solo_flota_taller` *(boolean, opcional, default: true)*: Filtra buses operativos del taller (sin restricciones numéricas artificiales).
- **Payload:** Ninguno.
- **Respuesta (`List[BusAutocompleteDTO]` - 200 OK):**
```json
[
  {
    "id": 12,
    "n_bus": "339",
    "patente": "ABCD-12",
    "marca": "Marcopolo",
    "modelo": "Paradiso 1800",
    "tipo_bus": "Doble Piso",
    "is_active": true,
    "en_taller": true
  }
]
```

---

### 4.3 `GET /api/v1/buses/{bus_id}`
- **Autenticación:** Pública.
- **Propósito:** Obtener la ficha técnica detallada de un bus por su ID interno primario.
- **Parámetros Path:**
  - `bus_id` *(integer, obligatorio, ge: 1)*: ID único del bus en base de datos.
- **Payload:** Ninguno.
- **Respuesta (`BusResponseDTO` - 200 OK):** Ficha técnica con atributos de carrocería, motor, chasis, año, capacidad y estado en taller.

---

### 4.4 `GET /api/v1/buses/numero/{n_bus}`
- **Autenticación:** Pública.
- **Propósito:** Obtener la ficha técnica completa de un bus a partir de su número de máquina visible (ej: `"339"`).
- **Parámetros Path:**
  - `n_bus` *(string, obligatorio)*: Número visible del bus.
- **Payload:** Ninguno.
- **Respuesta (`BusResponseDTO` - 200 OK):** Ficha técnica completa del bus.

---

### 4.5 `PATCH /api/v1/buses/{bus_id}/en-taller`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Control de entrada y salida física al patio del taller. Permite al supervisor actualizar manualmente si un bus está o no dentro del taller y registrar el motivo.
- **Parámetros Path:**
  - `bus_id` *(integer, obligatorio, ge: 1)*: ID del bus.
- **Payload (`BusUpdateEnTallerDTO` - `application/json`):**
```json
{
  "en_taller": true,
  "motivo": "Ingreso a patio por reporte de calentamiento de motor"
}
```
  - **Explicación de campos del Payload:**
    - `en_taller` *(boolean, obligatorio)*: `true` si el bus entra físicamente al taller; `false` si egresa.
    - `motivo` *(string, opcional)*: Justificación u observación administrativa del movimiento del vehículo.
- **Respuesta (`BusResponseDTO` - 200 OK):** Ficha del bus con el estado `en_taller` actualizado.

---

### 4.6 `POST /api/v1/buses`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Creación y catalogación de un nuevo bus en la flota.
- **Payload (`BusCreateDTO` - `application/json`):**
```json
{
  "patente": "KKL-909",
  "n_bus": "909",
  "marca": "Scania",
  "modelo": "K360",
  "tipo_bus": "Interurbano",
  "anio": 2022,
  "en_taller": false
}
```
  - **Explicación de campos del Payload:**
    - `patente` *(string, obligatorio, 6-10 caracteres)*: Placa patente del vehículo (se normaliza a mayúsculas automáticamente).
    - `n_bus` *(string, obligatorio, 1-10 caracteres)*: Número identificador visible de la máquina.
    - `marca` *(string, opcional)*: Marca del chasis/fabricante (ej: Scania, Mercedes-Benz, Volvo).
    - `modelo` *(string, opcional)*: Modelo de la unidad (ej: K360, Paradiso 1200).
    - `tipo_bus` *(string, opcional)*: Clasificación (ej: Doble Piso, Salón Cama, Clásico).
    - `anio` *(integer, opcional, 1990-2050)*: Año de fabricación.
    - `en_taller` *(boolean, opcional, default: false)*: Si el bus ingresa directamente al taller.
- **Respuesta (`BusResponseDTO` - 201 Created):**
```json
{
  "id": 45,
  "patente": "KKL-909",
  "n_bus": "909",
  "marca": "Scania",
  "modelo": "K360",
  "tipo_bus": "Interurbano",
  "anio": 2022,
  "is_active": true,
  "en_taller": false,
  "fecha_creacion": "2026-09-15T17:20:00",
  "fecha_baja": null,
  "motivo_baja": null,
  "usuario_baja_id": null
}
```
- **Errores:** `409 Conflict` si la patente o el número de máquina ya existen; `403 Forbidden` si el usuario no es supervisor ni admin.

---

### 4.7 `PATCH /api/v1/buses/{bus_id}/dar-de-baja` y `DELETE /api/v1/buses/{bus_id}`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Dar de baja / retirar de circulación una máquina del sistema con auditoría completa (`is_active = False`).
- **Parámetros Path:**
  - `bus_id` *(integer, obligatorio, ge: 1)*: ID del bus.
- **Payload (`BusDarDeBajaDTO` - `application/json`, opcional para DELETE):**
```json
{
  "motivo": "Venta de unidad por renovación de flota",
  "forzar": false
}
```
  - **Explicación de campos del Payload:**
    - `motivo` *(string, opcional)*: Razón o justificación de la baja de la unidad (ej: siniestro, venta, chatarrización).
    - `forzar` *(boolean, opcional, default: false)*: Si es `false`, el sistema valida que no existan órdenes de trabajo activas en taller para este bus (`422 BusinessRuleException`). Si es `true`, permite dar de baja aun cuando existan OTs activas pendientes de cierre.
- **Respuesta (`BusResponseDTO` - 200 OK):** Ficha del bus con `is_active: false`, `fecha_baja`, `motivo_baja` y `usuario_baja_id` registrados.

---

### 4.8 `PATCH /api/v1/buses/{bus_id}/reactivar`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Reincorporar y reactivar un bus previamente dado de baja (`is_active = True`, limpiando `fecha_baja` y `motivo_baja`).
- **Parámetros Path:**
  - `bus_id` *(integer, obligatorio, ge: 1)*: ID del bus.
- **Payload:** Ninguno.
- **Respuesta (`BusResponseDTO` - 200 OK):** Ficha del bus con `is_active: true`.

---

## 5. Módulo 3: Formulario Operativo de Neumáticos (`/formularioNeumatico`)

### 5.1 `GET /api/v1/formularioNeumatico`
- **Autenticación:** Pública.
- **Propósito:** Consulta de recepción y validación de disponibilidad del servicio de neumáticos.
- **Payload:** Ninguno.
- **Respuesta (200 OK):**
```json
{
  "status": "success",
  "message": "Solicitud de formularioNeumatico recibida correctamente",
  "data": null
}
```

---

### 5.2 `POST /api/v1/formularioNeumatico`
- **Autenticación:** Pública / Vinculada al `usuario_id` remitente.
- **Content-Type:** `multipart/form-data`.
- **Propósito:** Registro operativo de intervenciones, recambios y reparaciones de neumáticos de la flota. Persiste los datos en BD vinculando automáticamente el bus por su máquina y almacena la fotografía de evidencia física en el disco local (`/uploads/evidencias/`).
- **Payload (Campos Form-Data):**
  - `usuario_id` *(integer, opcional)*: ID del usuario (chofer o mecánico) que reporta.
  - `maquina` *(string, opcional)*: Número de máquina del bus (ej: `"339"`). Si coincide con un bus registrado, vincula el `bus_id`.
  - `tipo_bus` *(string, opcional)*: Tipo de bus (ej: `"Doble Piso"`, `"Interurbano"`).
  - `ruedas` *(string, opcional)*: Cadena de texto o JSON array indicando las posiciones afectadas (ej: `'["DI", "DD"]'`).
  - `motivo` *(string, opcional)*: Razón de la intervención (ej: `"Desgaste irregular"`, `"Pinchadura en ruta"`, `"Reencauche"`).
  - `precio` *(string, opcional)*: Costo de la operación o neumático. Admite separadores de miles y comas (ej: `"180.000"`). El servicio lo convierte automáticamente a `float`.
  - `marca_fuego` *(string, opcional)*: Código de marca de fuego vulcanizada en el neumático para control patrimonial.
  - `evidencia` *(archivo UploadFile, opcional)*: Archivo de imagen adjunto (JPG/PNG). Se renombra con UUID único en el servidor.
- **Explicación del Payload:**
  - Permite documentar el ciclo de vida del neumático, justificar costos de taller y mantener la evidencia fotográfica auditable.
- **Respuesta (JSON - 200 OK):**
```json
{
  "status": "success",
  "message": "Formulario de neumáticos procesado y guardado exitosamente",
  "reporte_id": 4,
  "bus_id": 12,
  "resumen": "Datos recibidos del formulario: UsuarioID=5, Máquina='339'...",
  "datos_recibidos": {
    "usuario_id": 5,
    "maquina": "339",
    "bus_id": 12,
    "tipo_bus": "Doble Piso",
    "ruedas": ["DI", "DD"],
    "motivo": "Desgaste irregular",
    "precio": "180.000",
    "marca_fuego": "MF-4501",
    "evidencia_original": "neumatico_danado.jpg",
    "evidencia_url": "/uploads/evidencias/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d.jpg"
  }
}
```

---

## 6. Módulo 4: Mantención de Taller y Pauta Preventiva (`/mantencion`)

### 6.1 `GET /api/v1/mantencion/pauta/items`
- **Autenticación:** Token Bearer (`require_current_user`).
- **Propósito:** Retorna el catálogo maestro estandarizado de las 11 inspecciones preventivas que el taller debe chequear antes de liberar cualquier máquina.
- **Payload:** Ninguno.
- **Respuesta (`List[PautaTallerItemDTO]` - 200 OK):**
```json
[
  {
    "id": 1,
    "categoria": "Motor y Fluidos",
    "item": "Nivel y estado de aceite de motor",
    "orden": 1,
    "is_active": true
  },
  {
    "id": 2,
    "categoria": "Motor y Fluidos",
    "item": "Nivel de refrigerante y fugas visibles",
    "orden": 2,
    "is_active": true
  }
]
```

---

### 6.2 `GET /api/v1/mantencion/categorias`
- **Autenticación:** Pública.
- **Propósito:** Retorna las categorías activas de fallas del taller (Frenos, Transmisión, Eléctrico, Suspensión, etc.).
- **Payload:** Ninguno.
- **Respuesta (`List[CategoriaFallaDTO]` - 200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Sistema de Frenos",
    "is_active": true
  }
]
```

---

### 6.3 `GET /api/v1/mantencion/fallas`
- **Autenticación:** Pública.
- **Propósito:** Retorna el catálogo de fallas preconfiguradas para selección rápida en formularios de choferes.
- **Parámetros Query:**
  - `categoria_id` *(integer, opcional)*: Filtra fallas por una categoría específica.
- **Payload:** Ninguno.
- **Respuesta (`List[FallaTallerDTO]` - 200 OK):** Lista de fallas con su categoría asociada.

---

### 6.4 `POST /api/v1/mantencion/solicitudes`
- **Autenticación:** Token Bearer (`require_conductor_or_admin`).
- **Propósito:** Creación de una orden/solicitud de taller por parte del conductor. Establece automáticamente el bus con `en_taller = True`. Admite dos modalidades de envío en **1 solo request HTTP** (eliminando pasos previos y cuellos de botella de subida):
  1. `application/json`: Payload tradicional enviando `foto_url` preexistente.
  2. `multipart/form-data`: Envío simultáneo de los datos del formulario y el archivo fotográfico adjunto (`foto`), almacenándolo automáticamente en **Google Cloud Storage** a través del servicio interno de backend sin requerir endpoints separados.
- **Payload Modalidad 1 (`application/json`):**
```json
{
  "n_bus": "339",
  "bus_id": 12,
  "descripcion_general": "Pérdida de potencia en pendientes y ruido en frenos delanteros",
  "foto_url": "https://storage.googleapis.com/narbus-taller-media/solicitudes/foto1.jpg",
  "detalles": [
    {
      "categoria_id": 1,
      "descripcion_personalizada": "Pastillas delanteras al límite de desgaste"
    },
    {
      "categoria_id": 2,
      "descripcion_personalizada": "Luz baja quemada"
    },
    {
      "falla_id": 3,
      "descripcion_personalizada": "Detalle técnico específico opcional"
    }
  ]
}
```
- **Payload Modalidad 2 (`multipart/form-data` - Recomendado con archivo adjunto):**
  - `n_bus` *(string)*: "339"
  - `bus_id` *(integer, opcional)*: 12
  - `descripcion_general` *(string, opcional)*: "Pérdida de potencia..."
  - `foto` *(binary/file, opcional)*: Archivo de imagen (.jpg, .jpeg, .png, .webp).
  - `detalles` *(JSON string, opcional)*: `[{"categoria_id": 1, "descripcion_personalizada": "..."}]`
  - **Explicación de campos del Payload:**
    - `n_bus` *(string, obligatorio)*: Número visible del bus reportado.
    - `bus_id` *(integer, opcional)*: ID primario del bus. Si no se provee, se resuelve automáticamente por el `n_bus`.
    - `descripcion_general` *(string, opcional)*: Resumen descriptivo de la condición del bus.
    - `foto_url` *(string, opcional)*: Enlace web a foto previa si existe.
    - `detalles` *(array de objetos, opcional)*: Desglose atómico de averías reportadas:
      - `categoria_id` *(integer, opcional - RECOMENDADO PARA CHOFER)*: ID de la categoría macro seleccionada (1: FRENOS, 2: ELECTRICO, 3: MOTOR, 4: CARROCERIA, 5: CLIMATIZACION, 6: OTRO). Si se envía este campo sin `falla_id`, el backend resuelve automáticamente la falla representativa de la categoría.
      - `falla_id` *(integer, opcional)*: ID de falla preconfigurada del catálogo técnico maestro (opcional, uso técnico).
      - `descripcion_personalizada` *(string, opcional)*: Texto libre u observación del conductor detallando los síntomas.
- **Respuesta (`SolicitudDTO` - 201 Created):** Objeto completo de la solicitud creada con estado `"REPORTADO"`. Cada detalle en `detalles` incluye directamente los campos `categoria_id` y `categoria_nombre` (ej. `"FRENOS"`), facilitando su visualización directa en Frontend sin recorrer anidaciones.

---

### 6.5 `GET /api/v1/mantencion/pendientes`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Bandeja principal de trabajo del mecánico (Pestaña 1). Lista todos los buses que están esperando atención en taller (estados `REPORTADO`, `PENDIENTE`).
- **Payload:** Ninguno.
- **Respuesta (`List[SolicitudDTO]` - 200 OK):** Lista de solicitudes pendientes ordenadas cronológicamente.

---

### 6.6 `GET /api/v1/mantencion/mis-trabajos`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Bandeja personal del mecánico (Pestaña 2). Retorna exclusivamente aquellas órdenes de trabajo donde el mecánico autenticado tiene fallas asignadas activamente.
- **Payload:** Ninguno.
- **Respuesta (`List[SolicitudDTO]` - 200 OK):** Lista de órdenes activas del mecánico.

---

### 6.7 `GET /api/v1/mantencion/{id}`
- **Autenticación:** Token Bearer (`require_current_user`).
- **Propósito:** Consulta completa de una solicitud: datos del bus, fallas detalladas, mecánicos asignados a cada falla, bitácora de comentarios y respuestas de pauta preventiva.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload:** Ninguno.
- **Respuesta (`SolicitudDTO` - 200 OK):** Ficha íntegra de la orden de taller.

---

### 6.8 `GET /api/v1/mantencion/{id}/pauta`
- **Autenticación:** Token Bearer (`require_current_user`).
- **Propósito:** Consulta el estado de avance y respuestas registradas en la pauta preventiva de 11 ítems para una solicitud específica.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload:** Ninguno.
- **Respuesta (`PautaEstadoResumenDTO` - 200 OK):**
```json
{
  "total_items": 11,
  "respondidos": 10,
  "pendientes": 1,
  "completado": false,
  "items_con_defecto": 1,
  "respuestas": [
    {
      "id": 101,
      "solicitud_id": 7,
      "item_id": 1,
      "item_categoria": "Motor y Fluidos",
      "item_nombre": "Nivel y estado de aceite de motor",
      "estado": "OK",
      "observacion": null,
      "mecanico_id": 5,
      "mecanico_nombre": "Juan Pérez",
      "fecha_registro": "2026-09-03T10:00:00"
    }
  ]
}
```

---

### 6.9 `POST /api/v1/mantencion/{id}/pauta`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Guarda o actualiza en bloque las evaluaciones de los ítems de la pauta preventiva realizadas por el mecánico.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`PautaBatchUpdateDTO` - `application/json`):**
```json
{
  "respuestas": [
    {
      "item_id": 1,
      "estado": "OK",
      "observacion": "Nivel adecuado"
    },
    {
      "item_id": 3,
      "estado": "DEFECTO",
      "observacion": "Fuga visible en manguera de retorno"
    },
    {
      "item_id": 11,
      "estado": "NO_APLICA",
      "observacion": "No aplica a este modelo de bus"
    }
  ]
}
```
  - **Explicación de campos del Payload:**
    - `respuestas` *(array de objetos, obligatorio)*: Lista de evaluaciones individuales.
      - `item_id` *(integer, obligatorio)*: ID del ítem de pauta evaluado (1 a 11).
      - `estado` *(string, obligatorio)*: Calificación técnica. Debe ser exactamente: `"OK"`, `"DEFECTO"`, o `"NO_APLICA"`.
      - `observacion` *(string, opcional)*: Detalle técnico explicativo (obligado moralmente si el estado es `"DEFECTO"`).
- **Respuesta (`PautaEstadoResumenDTO` - 200 OK):** Resumen actualizado con los contadores de ítems respondidos, pendientes y con defecto.

---

### 6.10 `POST /api/v1/mantencion/{id}/autoasignar`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Autoasignación atómica de fallas por parte de un mecánico. El mecánico escoge las averías específicas en las que trabajará y puede opcionalmente asociar colaboradores (`colaboradores_ids`). Si otro mecánico ya estaba trabajando en una de ellas, ambos quedan como co-responsables activos. Cambia el estado de la orden a `EN_REPARACION`.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`AutoasignarFallasDTO` - `application/json`):**
```json
{
  "detalles_ids": [21, 22],
  "comentario": "Iniciando desmontaje de pastillas de freno con apoyo de equipo",
  "colaboradores_ids": [3, 4]
}
```
  - **Explicación de campos del Payload:**
    - `detalles_ids` *(array de integers, obligatorio)*: IDs de las fallas (`solicitud_detalles.id`) que el mecánico toma para reparar.
    - `comentario` *(string, opcional)*: Nota de inicio registrada automáticamente en la bitácora.
    - `colaboradores_ids` *(array de integers, opcional)*: IDs de mecánicos colaboradores a autoasignar atómicamente a las mismas fallas, registrando su presencia activa.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud con las nuevas asignaciones atómicas y mecánicos activos.


---

### 6.11 `POST /api/v1/mantencion/{id}/asignar`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Asignación atómica formal de fallas realizada por la supervisora o administrador a un mecánico en particular.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`AsignarFallasSupervisoraDTO` - `application/json`):**
```json
{
  "mecanico_id": 5,
  "detalles_ids": [21],
  "comentario": "Asignado por turno de mañana para despacho urgente"
}
```
  - **Explicación de campos del Payload:**
    - `mecanico_id` *(integer, obligatorio)*: ID del mecánico al que se le asignan las averías.
    - `detalles_ids` *(array de integers, obligatorio)*: Lista de IDs de fallas a asignarle.
    - `comentario` *(string, opcional)*: Instrucción u observación del supervisor.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud actualizada con la asignación atómica.

---

### 6.12 `POST /api/v1/mantencion/{id}/terminar-avance`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Cierre de jornada o término de sesión de avance en la solicitud (individual o de cuadrilla). Cuando cualquier mecánico del equipo lo ejecuta, finaliza la sesión activa de **todos los mecánicos involucrados**, registrando automáticamente `fecha_desasignacion` y `duracion_minutos` para cada integrante. Si no quedan mecánicos activos en la orden, conmuta automáticamente el estado a `PENDIENTE`.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`TerminarAvanceDTO` - `application/json`):**
```json
{
  "comentario": "Se cambiaron pastillas delanteras; queda pendiente purga de frenos",
  "detalles_ids": [21]
}
```
  - **Explicación de campos del Payload:**
    - `comentario` *(string, opcional)*: Novedades o estado en que deja las piezas la cuadrilla para el siguiente turno.
    - `detalles_ids` *(array de integers, opcional)*: IDs de averías específicas a cerrar para el equipo. Si se omite o es `null`, cierra todas las averías activas de la cuadrilla en la solicitud.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud con el historial actualizado y tiempos cronometrados de cada integrante.

---

### 6.13 `POST /api/v1/mantencion/{id}/detalles`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Permite a un mecánico o supervisor agregar formalmente una nueva avería detectada durante la inspección o reparación en taller, desacoplada de la bitácora de comentarios.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`AgregarFallaDTO` - `application/json`):**
```json
{
  "categoria_id": 1,
  "falla_id": null,
  "descripcion_personalizada": "Pastillas delanteras agrietadas descubiertas al desmontar caliper",
  "autoasignar": true
}
```
  - **Explicación de campos del Payload:**
    - `categoria_id` *(integer, opcional)*: ID de la categoría macro seleccionada (1: FRENOS, 2: ELECTRICO, 3: MOTOR, 4: CARROCERIA, 5: CLIMATIZACION, 6: OTRO).
    - `falla_id` *(integer, opcional)*: ID de falla técnica del catálogo maestro preconfigurado.
    - `descripcion_personalizada` *(string, opcional)*: Descripción técnica detallada del hallazgo.
    - `autoasignar` *(boolean, opcional, default: true)*: Si es `true`, el mecánico que la agrega se la autoasigna inmediatamente y la solicitud conmuta a `EN_REPARACION`. Si es `false`, la falla queda pendiente sin asignar.
- **Regla de Negocio:** Si la orden ya está en estado `FINALIZADO`, retorna error `422 BusinessRuleException` (*"No se pueden agregar fallas a una solicitud que ya ha sido finalizada"*).
- **Respuesta (`SolicitudDTO` - 201 Created):** Solicitud actualizada con la nueva falla en la lista `detalles` y la anotación automática en la bitácora.

---

### 6.13 `POST /api/v1/mantencion/{id}/tomar` *(Flujo Tradicional / Legado)*
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Autoasignación tradicional del bus completo como líder de equipo e invitación de colaboradores globales.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`TomarTrabajoDTO` - `application/json`):**
```json
{
  "colaboradores_ids": [6, 7],
  "colaboradores_nombres": ["Pedro Ayudante"],
  "comentario_inicial": "Equipo completo tomando el bus"
}
```
  - **Explicación de campos del Payload:**
    - `colaboradores_ids` *(array de integers, opcional)*: IDs de otros mecánicos invitados al equipo.
    - `colaboradores_nombres` *(array de strings, opcional)*: Nombres de colaboradores si no tienen cuenta en BD.
    - `comentario_inicial` *(string, opcional)*: Nota de apertura de trabajos.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud en estado `EN_REPARACION`.

---

### 6.14 `POST /api/v1/mantencion/{id}/desasignarme`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Salida individual de un mecánico del equipo de trabajo de la solicitud ("Salir del Equipo").
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Parámetros Query:**
  - `comentario` *(string, opcional)*: Motivo de la salida individual.
- **Payload:** Ninguno.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud actualizada con el mecánico desasignado.

---

### 6.15 `POST /api/v1/mantencion/{id}/liberar-turno`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Entrega masiva de turno del equipo completo ("Entregar / Pasar Turno"). Desasigna a todos los mecánicos activos y traslada la solicitud a `PENDIENTE`.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`LiberarTurnoDTO` - `application/json`):**
```json
{
  "comentario": "Cambio de turno noche. Se probaron inyectores y falta calibrar."
}
```
  - **Explicación de campos del Payload:**
    - `comentario` *(string, opcional)*: Informe general de entrega para el turno entrante.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud en estado `PENDIENTE`.

---

### 6.16 `PATCH /api/v1/mantencion/{id}/detalles/{detalle_id}/check`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Marcar o desmarcar el check de una falla resuelta. Registra la fecha exacta (`fecha_resolucion`) y el ID del mecánico que la marcó.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
  - `detalle_id` *(integer, obligatorio)*: ID de la falla (`solicitud_detalles.id`).
- **Parámetros Query:**
  - `resuelto` *(boolean, obligatorio)*: `true` para marcar resuelta; `false` para reabrirla.
- **Payload:** Ninguno.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud con el detalle actualizado.

---

### 6.17 `PATCH /api/v1/mantencion/{id}/detalles/{detalle_id}/repuesto`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Declarar que la resolución de una falla está bloqueada por falta de repuestos. Dispara inmediatamente una alerta operacional al supervisor.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
  - `detalle_id` *(integer, obligatorio)*: ID de la falla.
- **Payload (`ReportarRepuestoDTO` - `application/json`):**
```json
{
  "falta_repuesto": true,
  "comentario": "Se necesita retén de caja de cambios código RT-889"
}
```
  - **Explicación de campos del Payload:**
    - `falta_repuesto` *(boolean, opcional, default: true)*: `true` si falta repuesto; `false` si el repuesto ya llegó y se desbloquea.
    - `comentario` *(string, opcional)*: Especificación del repuesto solicitado o número de parte.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud con el flag `falta_repuesto` actualizado en la avería.

---

### 6.18 `POST /api/v1/mantencion/{id}/agregar-colaborador`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Agregar a un mecánico adicional al equipo mientras la solicitud está `EN_REPARACION`.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`AgregarColaboradorDTO` - `application/json`):**
```json
{
  "colaborador_id": 8,
  "colaborador_nombre": "Roberto Díaz"
}
```
  - **Explicación de campos del Payload:**
    - `colaborador_id` *(integer, opcional)*: ID del mecánico registrado en BD.
    - `colaborador_nombre` *(string, opcional)*: Nombre de apoyo si no posee cuenta registrada.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud con el colaborador incorporado.

---

### 6.19 `POST /api/v1/mantencion/{id}/comentarios`
- **Autenticación:** Token Bearer (`require_current_user`).
- **Propósito:** Agregar una nota a la bitácora cronológica inmutable de la solicitud (para choferes, mecánicos o supervisores).
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`ComentarioCreateDTO` - `application/json`):**
```json
{
  "comentario": "El repuesto ya fue comprado en bodega local y está en camino",
  "tipo": "GENERAL"
}
```
  - **Explicación de campos del Payload:**
    - `comentario` *(string, obligatorio)*: Mensaje de la bitácora.
    - `tipo` *(string, opcional, default: "GENERAL")*: Tipo de comentario (`GENERAL`, `AVANCE`, `BLOQUEO`, `TURNO`, `CIERRE`).
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud con el comentario añadido en `comentarios`.

---

### 6.20 `POST /api/v1/mantencion/{id}/finalizar`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Cierre formal de los trabajos de la solicitud (`estado = FINALIZADO`). Si se cumplen las condiciones, libera el bus de taller (`en_taller = False`). Valida pauta preventiva y fallas pendientes exigiendo justificaciones si existen pendientes.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`FinalizarSolicitudDTO` - `application/json`):**
```json
{
  "comentario_cierre": "Reparación concluida satisfactoriamente y probado en ruta corta",
  "motivo_incompleto_checklist": "No se evaluó aire acondicionado por clima frío",
  "motivo_cierre_parcial": null,
  "liberar_bus_taller": true
}
```
  - **Explicación de campos del Payload:**
    - `comentario_cierre` *(string, opcional)*: Informe de cierre técnico del mecánico.
    - `motivo_incompleto_checklist` *(string, condicional)*: **Obligatorio** si no se respondieron los 11 ítems de la pauta preventiva. Si la pauta está incompleta y este campo viene nulo o vacío, el backend rechaza con `422 Unprocessable Content` (`BUSINESS_RULE_VIOLATION`).
    - `motivo_cierre_parcial` *(string, condicional)*: **Obligatorio** si la solicitud se cierra con averías pendientes o bloqueadas por repuesto. Si hay fallas no resueltas y este campo se omite, retorna error `422`.
    - `liberar_bus_taller` *(boolean, opcional, default: true)*: Si es `true`, conmuta `en_taller = False` en la ficha del bus liberándolo para el servicio comercial.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud en estado `FINALIZADO`.

---

### 6.21 `POST /api/v1/mantencion/{id}/liberar`
- **Autenticación:** Token Bearer (`require_mecanico_or_admin`).
- **Propósito:** Alias semántico de cierre y liberación del bus de taller. Utiliza el DTO `LiberarSolicitudDTO` (heredero de `FinalizarSolicitudDTO`).
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`LiberarSolicitudDTO` - `application/json`):**
  - Mismos campos y reglas de validación condicional que en `POST /mantencion/{id}/finalizar`.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud finalizada y bus liberado.

---

## 7. Módulo 5: Supervisión, KPIs y Auditoría de Taller (`/supervision`)

### 7.1 `GET /api/v1/supervision/alertas`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Centro de Alertas en vivo para la supervisora. Escanea la base de datos y retorna tres tipos críticos de alertas operacionales:
  1. `REPUESTO_FALTANTE` *(Severidad: ALTA)*: Fallas activas detenidas por falta de repuestos.
  2. `DEFECTO_PAUTA` *(Severidad: CRITICA)*: Ítems de la pauta preventiva de 11 puntos marcados con estado `"DEFECTO"`.
  3. `BUS_SIN_MECANICOS` *(Severidad: MEDIA)*: Solicitudes en estado `EN_REPARACION` donde no hay ningún mecánico asignado activamente.
- **Payload:** Ninguno.
- **Respuesta (`List[AlertaSupervisionDTO]` - 200 OK):**
```json
[
  {
    "tipo": "REPUESTO_FALTANTE",
    "severidad": "ALTA",
    "solicitud_id": 7,
    "n_bus": "339",
    "mensaje": "Falla #21 bloqueada por falta de repuesto: retén código RT-889",
    "detalle_id": 21,
    "fecha_deteccion": "2026-09-03T09:30:00"
  },
  {
    "tipo": "DEFECTO_PAUTA",
    "severidad": "CRITICA",
    "solicitud_id": 7,
    "n_bus": "339",
    "mensaje": "Ítem de pauta 'Nivel de refrigerante y fugas visibles' evaluado con DEFECTO: Fuga visible en manguera de retorno",
    "detalle_id": null,
    "fecha_deteccion": "2026-09-03T10:15:00"
  }
]
```

---

### 7.2 `GET /api/v1/supervision/auditoria/buses-taller`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Tablero de auditoría y trazabilidad exhaustiva en vivo para supervisores y auditores. Permite inspeccionar el historial completo de solicitudes, cambios de turno cronometrados, resolución de averías y notas de bitácora.
- **Parámetros Query:**
  - `n_bus` *(string, opcional)*: Filtrar por número de bus específico (ej: `"339"`).
  - `estado` *(string, opcional)*: Filtrar por estado (`REPORTADO`, `PENDIENTE`, `EN_REPARACION`, `LIBERADO`, `FINALIZADO`).
  - `mecanico_nombre` *(string, opcional)*: Búsqueda de órdenes donde haya participado un mecánico por su nombre, apellido o username.
- **Payload:** Ninguno.
- **Respuesta (`List[SolicitudDTO]` - 200 OK):** Lista de solicitudes completas con todo su historial de auditoría.

---

### 7.3 `GET /api/v1/supervision/resumen-taller`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Dashboard ejecutivo con métricas de taller, KPIs de rendimiento, porcentaje de averías resueltas, categorización de fallas más comunes y alertas operativas consolidadas.
- **Payload:** Ninguno.
- **Respuesta (`ResumenTallerDTO` - 200 OK):**
```json
{
  "fecha_generacion": "2026-09-03T10:30:00",
  "metricas_estado": {
    "total_solicitudes": 52,
    "reportadas": 2,
    "pendientes": 4,
    "en_reparacion": 6,
    "liberadas": 1,
    "finalizadas": 39,
    "buses_fisicamente_en_taller": 13,
    "fallas_bloqueadas_por_repuesto": 2
  },
  "porcentaje_resolucion_fallas": 82.35,
  "total_fallas_registradas": 136,
  "total_fallas_resueltas": 112,
  "fallas_por_categoria": [
    {
      "categoria_id": 1,
      "categoria_nombre": "Sistema de Frenos",
      "total_fallas": 48
    },
    {
      "categoria_id": 2,
      "categoria_nombre": "Motor y Fluidos",
      "total_fallas": 35
    }
  ],
  "buses_activos_taller": ["339", "250", "410", "502"],
  "alertas": [
    {
      "tipo": "REPUESTO_FALTANTE",
      "severidad": "ALTA",
      "solicitud_id": 7,
      "n_bus": "339",
      "mensaje": "Falla #21 bloqueada por falta de repuesto",
      "detalle_id": 21,
      "fecha_deteccion": "2026-09-03T09:30:00"
    }
  ]
}
```

---

### 7.4 `POST /api/v1/supervision/solicitudes/{id}/asignar`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Endpoint de conveniencia en el módulo de supervisión para que la jefa de taller asigne directamente fallas atómicas a un mecánico específico.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la solicitud.
- **Payload (`AsignarFallasSupervisoraDTO` - `application/json`):**
```json
{
  "mecanico_id": 5,
  "detalles_ids": [21],
  "comentario": "Asignación directa desde pantalla de supervisión"
}
```
  - **Explicación de campos del Payload:**
    - `mecanico_id` *(integer, obligatorio)*: ID del mecánico al que se le encarga la reparación.
    - `detalles_ids` *(array de integers, obligatorio)*: Lista de IDs de fallas a atender.
    - `comentario` *(string, opcional)*: Instrucción u observación técnica.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud actualizada con la asignación atómica.

---

### 7.5 `PATCH /api/v1/supervision/solicitudes/{id}/estado` y `PATCH /api/v1/mantencion/solicitudes/{id}/estado`
- **Autenticación:** Token Bearer (`require_supervisor_or_admin`).
- **Propósito:** Permite a la supervisora o administrador cambiar manualmente el estado del ciclo de vida de una orden de trabajo (OT) a cualquier estado canónico, registrando obligatoriamente la acción en la bitácora inmutable de comentarios con tipo `CAMBIO_ESTADO`, permitiendo una justificación opcional, controlando la liberación física del bus del taller en cierres y manejando reaperturas limpias.
- **Parámetros Path:**
  - `id` *(integer, obligatorio)*: ID de la orden de trabajo (`TallerSolicitud`).
- **Payload (`CambiarEstadoSolicitudDTO` - `application/json`):**
```json
{
  "estado": "PENDIENTE",
  "comentario": "Reasignando a turno vespertino por falta de tiempo",
  "liberar_bus_taller": false
}
```
  - **Explicación de campos del Payload:**
    - `estado` *(string enum, obligatorio)*: Nuevo estado canónico. Valores permitidos:
      - `"REPORTADO"`: Falla reportada sin iniciar atención.
      - `"PENDIENTE"`: Falla en espera de turno o disponibilidad.
      - `"EN_REPARACION"`: Falla en curso con mecánicos interviniendo.
      - `"LIBERADO"`: Bus egresado del taller con averías o repuestos pendientes (`en_taller = false`, `fecha_cierre = null`).
      - `"FINALIZADO"`: Orden concluida y cerrada al 100%.
    - `comentario` *(string, opcional, max 1000 caracteres)*: Razón o justificación del cambio de estado ingresada por la supervisora. Si se omite o envía vacío (`null` o `""`), el backend genera automáticamente una glosa canónica auditable con timestamp y autor (ej: `"[CAMBIO DE ESTADO] Transición administrativa de REPORTADO a PENDIENTE ejecutada por Supervisora"`).
    - `liberar_bus_taller` *(boolean, opcional, default: true)*: Aplica cuando `estado` es `"LIBERADO"` o `"FINALIZADO"`. Si es `true`, marca el bus con `en_taller = false` (egreso físico de maestranza). Si es `false`, mantiene el bus físicamente en taller.
- **Respuesta (`SolicitudDTO` - 200 OK):** Solicitud completa actualizada con su nuevo estado, `fecha_cierre` (o `null` si fue reabierta) y el nuevo comentario registrado en el arreglo `comentarios`.
- **Reglas de Negocio:**
  - Si se intenta transicionar al mismo estado en que ya se encuentra la orden, retorna `422 BusinessRuleException`.
  - Al transicionar a `"FINALIZADO"`, se setea `fecha_cierre = now()`, `mecanico_cierre_id = supervisor_id` y se desactivan automáticamente los mecánicos y asignaciones activas calculando sus duraciones.
  - Al transicionar desde `"FINALIZADO"` a un estado activo, se limpia la `fecha_cierre = null` y se vuelve a marcar el bus con `en_taller = true`.
