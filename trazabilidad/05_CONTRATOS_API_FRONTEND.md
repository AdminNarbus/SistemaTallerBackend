# Contratos de API para Frontend: Sistema Integral de Taller Narbus

> **Documento Oficial de Integración Frontend-Backend**  
> **Versión:** 3.0.0  
> **Fecha de Actualización:** 2026-09-09  
> **Rama Backend:** `feature/optimizacion-consultas-latencia-8800km`  
> **Estado:** 100% Implementado, verificado con 83/83 tests automatizados pasando y desplegado en local.  
> **Total Endpoints Activos:** 43 endpoints RESTful.

---

## 1. Novedades Principales y Decisiones de Arquitectura (v3.0.0)

Esta versión consolida los dos mayores hitos de ingeniería del Backend:
1. **Almacenamiento Cloud de Imágenes en Google Cloud Storage (GCS) en 1 Solo Request HTTP:**
   * **Cero Cuellos de Botella:** NO existe un endpoint previo de upload (`/uploads/imagen` fue descartado). El Frontend no realiza 2 peticiones secuenciales.
   * **Envío Atómico (`multipart/form-data`):** Tanto en creación de órdenes de mantención (`POST /api/v1/mantencion/solicitudes`) como en reportes de neumáticos (`POST /api/v1/formularioNeumatico`), el formulario y el archivo de imagen (`foto` o `evidencia`) se envían juntos en **una única llamada HTTP**.
   * **El Backend se encarga de todo:** Sube el archivo directamente a Google Cloud Storage mediante I/O no bloqueante (`asyncio.to_thread`) y guarda en PostgreSQL la URL pública HTTPS resultante (`foto_url` o `evidencia_url`).
   * **Cero Fotos Huérfanas:** Si el formulario falla validación de negocio, no queda ninguna imagen abandonada en la nube.
   * **Retrocompatibilidad 100%:** Si el frontend no tiene foto o ya posee una URL, puede seguir enviando `application/json` con `"foto_url": null | "https://..."`.
2. **Mitigación Radical de Latencia Transcontinental a 8.800 km (~140ms RTT a Neon Ohio):**
   * **Buses y Categorías Optimizadas:** `/api/v1/buses/buscar` retorna `BusSimpleDTO` con `id`, `n_bus` y `patente`. `/api/v1/mantencion/categorias` retorna cada categoría con su `falla_id` y `falla_nombre` precalculados.
   * **Creación Ultrarrápida de Solicitud (0 RTTs Previas):** Si el frontend envía `bus_id` y en `detalles` envía `falla_id` y `falla_nombre`, el backend realiza la inserción en **1 sola operación atómica** (ahorrando ~450ms de latencia en la red).
   * **Mutaciones Atómicas Ligeras (Nivel 3):** Los endpoints frecuentes del mecánico (`PATCH /check`, `PATCH /repuesto`, `POST /comentarios`) ya no devuelven la orden completa de 100 campos (`SolicitudDTO`), sino DTOs atómicos ultrarrápidos (`DetalleUpdateDTO` y `ComentarioAddedDTO`) en memoria tras el commit (~290ms en vez de ~450ms).
   * **Caché HTTP en Navegador:** Catálogos estáticos envían cabeceras `Cache-Control: private, max-age=300, stale-while-revalidate=60` y bandejas de entrada envían `max-age=15, stale-while-revalidate=30`, permitiendo navegación instantánea en React sin bloqueos de carga.
3. **Paginación Estándar en Listados:**
   * `/api/v1/mantencion/pendientes` y `/api/v1/mantencion/mis-trabajos` aceptan `limit` (default 50, máx 100) y `skip` (default 0).
   * `/api/v1/supervision/buses/taller` acepta `limit` (default 20, máx 100), `skip`, `estado` y `q`.
4. **Búsqueda Dinámica de Mecánicos:**
   * `GET /api/v1/auth/usuarios/buscar-mecanicos?query=...` permite autocompletar colaboradores por nombre sin quemar IDs en el frontend.

---

## 2. Formato Estándar de Respuestas y Excepciones

Todas las respuestas de error siguen de forma estricta la estructura de excepciones de dominio:

```json
{
  "error": {
    "code": "BUSINESS_RULE_VIOLATION | NOT_FOUND | CONFLICT | FORBIDDEN | HTTP_ERROR | VALIDATION_ERROR",
    "message": "Mensaje legible y descriptivo para el usuario final",
    "detail": null
  }
}
```

### Códigos de Estado HTTP Utilizados:
* `200 OK`: Operación de consulta, actualización o mutación exitosa.
* `201 Created`: Creación exitosa de entidad (`POST /solicitudes`, `POST /comentarios`, `POST /formularioNeumatico`).
* `401 Unauthorized`: Token JWT ausente, inválido o expirado.
* `403 Forbidden`: Usuario con rol insuficiente (ej. conductor intentando tomar un trabajo de mecánico).
* `404 Not Found`: Recurso no encontrado (bus, solicitud, detalle, etc.).
* `409 Conflict`: Conflicto de estado (ej. bus ya asignado en otro proceso o duplicado).
* `422 Unprocessable Content`: Violación de regla de negocio (`BUSINESS_RULE_VIOLATION`) o validación de schema Pydantic (`VALIDATION_ERROR`).

---

## 3. Manejo y Renderizado de Fotografías (Google Cloud Storage)

### 3.1 URLs Retornadas por el Backend
Tanto en mantención (`foto_url`) como en neumáticos (`evidencia_url`), la base de datos retorna:
* En **Producción (Google Cloud):** URL pública HTTPS absoluta: `https://storage.googleapis.com/narbus-taller-media/solicitudes/<uuid>.jpg`.
* En **Desarrollo Local:** Ruta relativa local: `/uploads/solicitudes/<uuid>.jpg`.

### 3.2 Función Utilitaria Recomendada para Frontend (`getFullImageUrl`)
Copia esta función en tu proyecto React/TypeScript para que todos los componentes `<img />` funcionen transparentemente tanto en local como en producción:

```typescript
// src/utils/imageUrl.ts
const BACKEND_URL = import.meta.env.VITE_API_URL?.replace('/api/v1', '') || 'http://localhost:8000';

export function getFullImageUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  
  // Si ya es una URL absoluta (Google Cloud Storage o CDN externa)
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }
  
  // Si es una ruta relativa local (/uploads/...)
  return `${BACKEND_URL}${url.startsWith('/') ? '' : '/'}${url}`;
}
```

**Uso en un componente:**
```tsx
<img 
  src={getFullImageUrl(solicitud.foto_url) || '/images/no-photo-bus.png'} 
  alt={`Foto de orden ${solicitud.n_bus}`}
  className="w-full h-48 object-cover rounded-lg"
/>
```

---

## 4. Módulo Autenticación y Usuarios (`/api/v1/auth`)

| Método | Endpoint | Roles | Descripción |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login` | Público | Login estándar con JSON (`LoginDTO`). Retorna `TokenDTO` con JWT Bearer y datos del usuario. |
| `POST` | `/api/v1/auth/login/token` | Público | Login OAuth2 Password Request Form (`username`, `password`). |
| `GET` | `/api/v1/auth/me` | Autenticado | Retorna el perfil completo del usuario autenticado (`UsuarioResponseDTO`). |
| `GET` | `/api/v1/auth/usuarios` | Supervisor, Admin | Listado de todos los usuarios registrados. |
| `POST` | `/api/v1/auth/usuarios` | Admin | Creación de nuevos usuarios con rol específico. |
| `DELETE`| `/api/v1/auth/usuarios/{id}` | Admin | Desactivación (soft delete) de usuario. |
| `GET` | `/api/v1/auth/usuarios/buscar-mecanicos` | Mecánico, Supervisor, Admin | Búsqueda por nombre de mecánicos activos para autocompletar colaboradores. |

### `GET /api/v1/auth/usuarios/buscar-mecanicos`
* **Query Params:** `query` (string, ej: `"juan"`).
* **Respuesta (200 OK):**
```json
[
  {
    "id": 4,
    "nombre_completo": "Juan Pérez",
    "email": "juan.perez@narbus.cl",
    "rol": "MECANICO"
  }
]
```

---

## 5. Módulo Buses (`/api/v1/buses`)

| Método | Endpoint | Roles | Descripción |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/buses` | Autenticado | Catálogo de buses. Parámetros: `solo_activos=true`, `solo_flota_taller=true` (200 a 899). |
| `GET` | `/api/v1/buses/buscar` | Autenticado | Búsqueda rápida por prefijo/número. Retorna `BusSimpleDTO`. |
| `GET` | `/api/v1/buses/{id}` | Autenticado | Detalle de un bus por su ID primario. |
| `GET` | `/api/v1/buses/numero/{n_bus}`| Autenticado | Detalle de un bus por su número de máquina (ej. `"330"`). |
| `PATCH`| `/api/v1/buses/{id}/en-taller`| Supervisor, Admin | Actualiza el flag físico `en_taller: boolean`. |

### `GET /api/v1/buses/buscar` (Contrato Optimizado)
* **Query Params:**
  * `query: string` (ej: `"33"`)
  * `solo_flota_taller: boolean` (default: `true`, restringe a `200 <= n_bus < 900`).
* **Respuesta (200 OK):**
```json
[
  {
    "id": 15,
    "n_bus": "330",
    "patente": "KLSW-89",
    "en_taller": false
  },
  {
    "id": 16,
    "n_bus": "331",
    "patente": "KLSW-90",
    "en_taller": true
  }
]
```

---

## 6. Módulo Mantención: Catálogos y Creación de Órdenes

### 6.1 `GET /api/v1/mantencion/categorias` (Catálogo con Cache)
* **Headers de Respuesta:** `Cache-Control: private, max-age=300, stale-while-revalidate=60`
* **Respuesta (200 OK):**
```json
[
  {
    "id": 1,
    "nombre": "Frenos y Aire",
    "is_active": true,
    "falla_id": 1,
    "falla_nombre": "Avería de Frenos y Aire"
  },
  {
    "id": 2,
    "nombre": "Motor y Transmisión",
    "is_active": true,
    "falla_id": 2,
    "falla_nombre": "Avería de Motor y Transmisión"
  }
]
```

### 6.2 `POST /api/v1/mantencion/solicitudes` (Creación en 1 Solo Request HTTP)
Soporta dos modalidades con detección automática de `Content-Type`:

#### Modalidad A: Envío con Foto Adjunta Directa (`multipart/form-data` - RECOMENDADA)
* **Content-Type:** `multipart/form-data`
* **Campos `FormData`:**
  * `n_bus`: `"330"` (string, obligatorio si no se envía `bus_id`).
  * `bus_id`: `15` (number, **altamente recomendado** para ahorrar búsqueda en BD).
  * `bus_patente`: `"KLSW-89"` (string, opcional).
  * `descripcion_general`: `"Pérdida de presión en frenos traseros"` (string, opcional).
  * `foto`: `File` / `Blob` (archivo de imagen .jpg, .jpeg, .png, .webp, máx 10 MB, opcional).
  * `detalles`: String JSON serializado con `JSON.stringify(detalles)`:
    ```json
    [
      {
        "falla_id": 1,
        "categoria_id": 1,
        "falla_nombre": "Avería de Frenos y Aire",
        "descripcion_personalizada": "Ruidos metálicos al frenar"
      }
    ]
    ```

#### Modalidad B: Envío JSON Tradicional (`application/json`)
Si no hay fotografía adjunta o si el cliente ya cuenta con la URL:
```json
POST /api/v1/mantencion/solicitudes
Content-Type: application/json

{
  "bus_id": 15,
  "n_bus": "330",
  "descripcion_general": "Pérdida de presión en frenos traseros",
  "foto_url": null,
  "detalles": [
    {
      "falla_id": 1,
      "categoria_id": 1,
      "falla_nombre": "Avería de Frenos y Aire",
      "descripcion_personalizada": "Ruidos metálicos al frenar"
    }
  ]
}
```

* **Respuesta (201 Created):** Retorna `SolicitudDTO` con estado `"REPORTADO"` y `foto_url` poblada con la URL de Google Cloud Storage.

---

## 7. Módulo Mantención: Pestañas de Trabajo del Mecánico

### 7.1 `GET /api/v1/mantencion/pendientes` (Buses Esperando en Taller)
* **Roles:** `MECANICO`, `SUPERVISOR`, `ADMIN`.
* **Query Params:**
  * `limit`: int (default `50`, máx `100`).
  * `skip`: int (default `0`).
* **Headers:** `Cache-Control: private, max-age=15, stale-while-revalidate=30`
* **Respuesta (200 OK):** `List[SolicitudResumenDTO]` (solicitudes en `REPORTADO` o `PENDIENTE`).

### 7.2 `GET /api/v1/mantencion/mis-trabajos` (Trabajos Activos del Mecánico)
* **Roles:** `MECANICO`, `ADMIN`.
* **Query Params:** `limit` (default 50), `skip` (default 0).
* **Headers:** `Cache-Control: private, max-age=15, stale-while-revalidate=30`
* **Respuesta (200 OK):** `List[SolicitudResumenDTO]` (órdenes en `EN_REPARACION` donde el usuario logueado está activamente asignado a al menos una falla).

### 7.3 `GET /api/v1/mantencion/{id}` (Detalle Completo de la Orden)
* **Respuesta (200 OK):** `SolicitudDTO` con todas las listas completas: `detalles`, `mecanicos`, `comentarios` y `pauta_respuestas`.

---

## 8. Módulo Mantención: Mutaciones Operacionales del Mecánico

### 8.1 `POST /api/v1/mantencion/{id}/autoasignar` (Toma Atómica de Fallas)
* **Roles:** `MECANICO`, `ADMIN`.
* **Descripción:** El mecánico selecciona qué fallas específicas desea reparar e invita opcionalmente a colaboradores (`colaboradores_ids`). Soporta co-responsabilidad atómica.
* **Payload:**
```json
{
  "detalles_ids": [12, 14],
  "comentario": "Iniciando reparación de zapatas en equipo",
  "colaboradores_ids": [4]
}
```
* **Respuesta (200 OK):** `SolicitudDTO`.

### 8.2 `POST /api/v1/mantencion/{id}/asignar` (Asignación por Supervisora)
* **Roles:** `SUPERVISOR`, `ADMIN`.
* **Payload:**
```json
{
  "mecanico_id": 4,
  "detalles_ids": [12],
  "comentario": "Asignado para soporte en turno tarde"
}
```
* **Respuesta (200 OK):** `SolicitudDTO`.

### 8.3 `POST /api/v1/mantencion/{id}/terminar-avance` (Cierre de Turno del Mecánico)
* **Roles:** `MECANICO`, `ADMIN`.
* **Descripción:** Registra el avance y finaliza la sesión activa del mecánico en sus fallas asignadas, calculando automáticamente la duración en minutos. Si no quedan mecánicos activos en la orden, conmuta automáticamente a `PENDIENTE`.
* **Payload:**
```json
{
  "detalles_ids": [12],
  "comentario": "Pastillas cambiadas; falta sangrado de aire por turno siguiente"
}
```
* **Respuesta (200 OK):** `SolicitudDTO`.

### 8.4 `PATCH /api/v1/mantencion/{id}/detalles/{detalle_id}/check` (Resolver Falla - DTO Atómico)
* **Roles:** `MECANICO`, `ADMIN`.
* **Descripción:** Marca o desmarca una falla como resuelta. Si la falla tiene `falta_repuesto=true`, el backend la rechaza con `HTTP 422 BusinessRuleException`.
* **Payload:**
```json
{
  "resuelto": true
}
```
* **Respuesta (200 OK - `DetalleUpdateDTO` Ultrarrápido ~290ms):**
```json
{
  "id": 12,
  "resuelto": true,
  "mecanico_resolvio_id": 3,
  "mecanico_resolvio_nombre": "Carlos Mecánico",
  "fecha_resolucion": "2026-09-09T18:20:00Z",
  "falta_repuesto": false,
  "comentario_repuesto": null
}
```
> **Tip Frontend:** Actualiza directamente el detalle correspondiente en tu estado local de React sin necesidad de volver a consultar todo el bus por red.

### 8.5 `PATCH /api/v1/mantencion/{id}/detalles/{detalle_id}/repuesto` (Bloqueo por Repuesto - DTO Atómico)
* **Roles:** `MECANICO`, `ADMIN`.
* **Payload:**
```json
{
  "falta_repuesto": true,
  "comentario": "Se requiere pulmón de freno Knorr de 24 pulgadas"
}
```
* **Respuesta (200 OK - `DetalleUpdateDTO` Ultrarrápido):**
```json
{
  "id": 12,
  "resuelto": false,
  "mecanico_resolvio_id": null,
  "mecanico_resolvio_nombre": null,
  "fecha_resolucion": null,
  "falta_repuesto": true,
  "comentario_repuesto": "Se requiere pulmón de freno Knorr de 24 pulgadas"
}
```

### 8.6 `POST /api/v1/mantencion/{id}/comentarios` (Agregar Nota - DTO Atómico)
* **Roles:** Autenticado.
* **Payload:**
```json
{
  "comentario": "Se probó en patio de maniobras a baja velocidad, sin ruidos anormales"
}
```
* **Respuesta (201 Created - `ComentarioAddedDTO` Ultrarrápido):**
```json
{
  "id": 55,
  "solicitud_id": 101,
  "autor_id": 3,
  "autor_nombre": "Carlos Mecánico",
  "comentario": "Se probó en patio de maniobras a baja velocidad, sin ruidos anormales",
  "fecha_creacion": "2026-09-09T18:30:00Z"
}
```

---

## 9. Módulo Mantención: Pauta Preventiva y Liberación del Bus

### 9.1 `GET /api/v1/mantencion/pauta/items` (Catálogo Maestro)
* **Headers:** `Cache-Control: private, max-age=300, stale-while-revalidate=60`
* Retorna los 11 ítems oficiales de inspección preventiva categorizados:
  1. Nivel y estado de aceite de motor
  2. Nivel de refrigerante y fugas visibles
  3. Fugas de aire y presión de tanques
  4. Estado y espesor de pastillas/balatas
  5. Luces exteriores reglamentarias
  6. Plumillas y lavaparabrisas
  7. Estado de correas auxiliares
  8. Baterías y bornes
  9. Estado y tensión de neumáticos
  10. Espejos y visibilidad
  11. Puertas y mecanismo neumático

### 9.2 `GET /api/v1/mantencion/{id}/pauta`
* Retorna el resumen de avance (`total_items: 11`, `respondidos`, `pendientes`, `completado`, `items_con_defecto`) y la lista de respuestas registradas.

### 9.3 `POST /api/v1/mantencion/{id}/pauta` (Guardado Batch en 1 Sola Transacción)
* **Payload:**
```json
{
  "respuestas": [
    { "item_id": 1, "estado": "OK", "observacion": "Nivel correcto en varilla" },
    { "item_id": 2, "estado": "DEFECTO", "observacion": "Abrazadera suelta con goteo menor" },
    { "item_id": 3, "estado": "NO_APLICA", "observacion": null }
  ]
}
```
* **Estados Permitidos:** `"OK"`, `"DEFECTO"`, `"NO_APLICA"`.
* **Respuesta (200 OK):** `PautaEstadoResumenDTO`.

### 9.4 `POST /api/v1/mantencion/{id}/liberar` (Cierre y Salida de Taller)
* **Roles:** `MECANICO`, `ADMIN`.
* **Reglas de Negocio Estrictas:**
  * Si la pauta no está 100% completada (`respondidos < 11`), **es obligatorio** enviar `motivo_incompleto_checklist`.
  * Si quedan averías con `resuelto=false` o `falta_repuesto=true`, **es obligatorio** enviar `motivo_cierre_parcial`.
* **Payload:**
```json
{
  "motivo_incompleto_checklist": "Ítems 9 al 11 omitidos por urgencia operacional",
  "motivo_cierre_parcial": "Falla de climatizador postergada hasta llegada de filtro",
  "comentario_cierre": "Bus apto para servicio con advertencia a tráfico",
  "liberar_bus_taller": true
}
```
* **Respuesta (200 OK):** `SolicitudDTO` con estado `"FINALIZADO"` y el bus liberado (`en_taller = false`).

---

## 10. Módulo Supervisión y Auditoría (`/api/v1/supervision`)

| Método | Endpoint | Roles | Descripción |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/supervision/resumen-taller` | Supervisor, Admin | KPIs globales, desglose de fallas por categoría y centro de alertas en tiempo real. |
| `GET` | `/api/v1/supervision/alertas` | Supervisor, Admin | Alertas operacionales activas (`REPUESTO_FALTANTE`, `DEFECTO_PAUTA`, `BUS_SIN_MECANICOS`). |
| `GET` | `/api/v1/supervision/buses/taller` | Supervisor, Admin | Paginación y auditoría profunda de buses en taller con filtros por estado y buscador. |

### `GET /api/v1/supervision/buses/taller` (Paginación y Auditoría)
* **Query Params:**
  * `limit`: int (default `20`, máx `100`).
  * `skip`: int (default `0`).
  * `estado`: string opcional (`"REPORTADO"`, `"PENDIENTE"`, `"EN_REPARACION"`, `"FINALIZADO"`, etc.).
  * `q`: string opcional (búsqueda por patente o `n_bus`).
* **Respuesta (200 OK):** `AuditoriaBusesPaginadaDTO`:
```json
{
  "total": 35,
  "page": 1,
  "limit": 20,
  "pages": 2,
  "items": [
    {
      "bus_id": 15,
      "n_bus": "330",
      "patente": "KLSW-89",
      "estado_taller": "EN_REPARACION",
      "en_taller": true,
      "solicitud_id": 101,
      "fecha_ingreso": "2026-09-09T08:00:00Z",
      "total_fallas": 3,
      "fallas_resueltas": 1,
      "fallas_pendientes": 2,
      "mecanicos_asignados": ["Carlos Mecánico", "Juan Pérez"],
      "pauta_completada": false,
      "alertas_activas": ["REPUESTO_FALTANTE"]
    }
  ]
}
```

---

## 11. Módulo Neumáticos (`/api/v1/neumaticos`)

* **Ruta de Producción:** `POST /api/v1/formularioNeumatico` (y alias RESTful `POST /api/v1/neumaticos/formularioNeumatico`).
* **Content-Type:** `multipart/form-data`
* **Campos `FormData`:**
  * `usuario_id`: int (opcional, se infiere del JWT si se envía Bearer).
  * `maquina`: `"330"` (string, número de máquina).
  * `tipo_bus`: `"DOBLE PISO"` (string).
  * `ruedas`: String JSON serializado con las posiciones seleccionadas: `"[1, 2, 5]"`.
  * `motivo`: `"CAMBIO POR DESGASTE"` (string).
  * `precio`: `"145000"` (string/number).
  * `marca_fuego`: `"NF-8821"` (string, opcional).
  * `evidencia`: `File` (archivo fotográfico adjunto).
* **Resultado Backend:** Sube la foto directamente a Google Cloud Storage (`evidencias/<uuid>.jpg`) y almacena la URL en `evidencia_url`.
* **Respuesta (201 Created):**
```json
{
  "status": "success",
  "message": "Formulario de neumático procesado exitosamente.",
  "reporte_id": 42,
  "bus_id": 15,
  "resumen": "Reporte registrado para máquina 330 con evidencia fotográfica.",
  "datos_recibidos": { ... }
}
```

---

## 12. Diccionario de Tipos e Interfaces TypeScript (Frontend)

Para copiar directamente en `src/types/api.ts`:

```typescript
export type EstadoSolicitud = 
  | 'REPORTADO' 
  | 'PENDIENTE' 
  | 'EN_REPARACION' 
  | 'LIBERADO' 
  | 'FINALIZADO';

export type EstadoItemPauta = 'OK' | 'DEFECTO' | 'NO_APLICA';

export interface BusSimpleDTO {
  id: number;
  n_bus: string;
  patente: string;
  en_taller: boolean;
}

export interface CategoriaFallaDTO {
  id: number;
  nombre: string;
  is_active: boolean;
  falla_id: number;
  falla_nombre: string;
}

export interface DetalleUpdateDTO {
  id: number;
  resuelto?: boolean;
  mecanico_resolvio_id?: number | null;
  mecanico_resolvio_nombre?: string | null;
  fecha_resolucion?: string | null;
  falta_repuesto?: boolean;
  comentario_repuesto?: string | null;
}

export interface ComentarioAddedDTO {
  id: number;
  solicitud_id: number;
  autor_id: number;
  autor_nombre: string | null;
  comentario: string;
  fecha_creacion: string;
}

export interface MecanicoAsignadoDTO {
  id: number;
  nombre: string;
  origen: 'AUTOASIGNADO' | 'SUPERVISOR';
  asignado_por_id: number | null;
  asignado_por_nombre: string | null;
  fecha_asignacion: string;
}

export interface SolicitudDetalleDTO {
  id: number;
  solicitud_id: number;
  categoria_id: number | null;
  categoria_nombre: string | null;
  falla_id: number | null;
  descripcion_personalizada: string | null;
  resuelto: boolean;
  mecanico_resolvio_id: number | null;
  mecanico_resolvio_nombre: string | null;
  falta_repuesto: boolean;
  comentario_repuesto: string | null;
  fecha_creacion: string;
  fecha_resolucion: string | null;
  mecanicos_asignados: MecanicoAsignadoDTO[];
}

export interface PautaRespuestaDTO {
  id: number;
  solicitud_id: number;
  item_id: number;
  item_categoria: string | null;
  item_nombre: string | null;
  estado: EstadoItemPauta;
  observacion: string | null;
  mecanico_id: number;
  mecanico_nombre: string | null;
  fecha_registro: string;
}

export interface SolicitudDTO {
  id: number;
  n_bus: string;
  bus_id: number | null;
  bus_patente: string | null;
  usuario_creador_id: number;
  usuario_creador_nombre: string | null;
  mecanico_cierre_id: number | null;
  mecanico_cierre_nombre: string | null;
  estado: EstadoSolicitud;
  descripcion_general: string | null;
  foto_url: string | null;
  motivo_incompleto_checklist: string | null;
  motivo_cierre_parcial: string | null;
  fecha_creacion: string;
  fecha_cierre: string | null;
  pauta_completada: boolean;
  total_fallas: number;
  fallas_resueltas: number;
  fallas_con_falta_repuesto: number;
  detalles: SolicitudDetalleDTO[];
  mecanicos: Array<{ id: number; usuario_id: number; usuario_nombre: string | null; activo: boolean }>;
  comentarios: ComentarioAddedDTO[];
  pauta_respuestas: PautaRespuestaDTO[];
}

export interface SolicitudResumenDTO extends SolicitudDTO {}

export interface PautaEstadoResumenDTO {
  total_items: number;
  respondidos: number;
  pendientes: number;
  completado: boolean;
  items_con_defecto: number;
  respuestas: PautaRespuestaDTO[];
}

export interface AlertaSupervisionDTO {
  tipo: 'REPUESTO_FALTANTE' | 'DEFECTO_PAUTA' | 'BUS_SIN_MECANICOS';
  severidad: 'ALTA' | 'MEDIA' | 'BAJA';
  solicitud_id: number;
  n_bus: string;
  detalle_id?: number | null;
  mensaje: string;
  fecha_deteccion: string;
}
```

---

## 13. Buenas Prácticas y Recomendaciones para la Interfaz de Usuario

1. **Envío de Fotos con Vista Previa Inmediata:**
   * Al seleccionar una imagen en el input file (`<input type="file" accept="image/*" />`), genera una URL en memoria con `URL.createObjectURL(file)` para mostrar el preview al instante.
   * Envía el formulario directamente con `FormData` en 1 solo request HTTP.
2. **Uso de Caché para Navegación Instantánea:**
   * Utiliza bibliotecas como TanStack React Query o SWR. Las respuestas del backend incluyen cabeceras `Cache-Control` con `stale-while-revalidate`. Configura `staleTime: 15_000` para listados y `staleTime: 300_000` para catálogos para evitar spinners repetitivos.
3. **Actualización Optimista en Chequeo de Averías:**
   * Al marcar una falla como resuelta (`PATCH /check`), actualiza el estado visual inmediatamente. El endpoint responde en ~290ms con el `DetalleUpdateDTO` confirmando el cambio.
4. **Modal de Cierre y Liberación:**
   * Condiciona la obligatoriedad de los campos en el modal:
     * Si `pauta_completada === false`, exige obligatoriamente `motivo_incompleto_checklist`.
     * Si `fallas_resueltas < total_fallas` o `fallas_con_falta_repuesto > 0`, exige obligatoriamente `motivo_cierre_parcial`.
