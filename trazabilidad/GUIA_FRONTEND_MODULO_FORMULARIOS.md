# Guía de Integración Frontend: Módulo Unificado de Formularios (`/api/v1/formularios`)

## 1. Visión General y Objetivos de la Migración

El backend ha centralizado todas las compuertas de entrada y checklists de inspección bajo un único módulo autónomo y de alta cohesión llamado **`formularios`** (`app/modules/formularios`).

### ¿Por qué este cambio?
1. **Separación de Responsabilidades (SRP):** El módulo `mantencion` se enfoca estrictamente en la gestión interna de la maestranza (cuadrillas de mecánicos, averías activas, pausas, cierres y estadías físicas), delegando las compuertas de entrada a `formularios`.
2. **Eliminación de Redundancia y Simplificación de Neumáticos:** Se eliminó la sobrecarga del formulario de neumáticos (adiós a `precio`/`monto` y al ingreso manual de `tipo_bus`, manteniendo `marca_fuego` opcional).
3. **Pauta Preventiva Desacoplada:** El checklist de 11 ítems estándar ahora se gestiona como un formulario independiente y reutilizable.

---

## 2. Tabla Comparativa de Endpoints (Rutas Antiguas vs. Nuevas)

| Dominio | Acción / Operación | Método | URL Antigua (Desaconsejada) | **Nueva URL Canónica (Oficial)** |
| --- | --- | :---: | --- | --- |
| **Neumáticos** | Enviar Formulario de Neumático | `POST` | `/api/v1/formularioNeumatico` | **`/api/v1/formularios/neumaticos`** |
| **Neumáticos** | Estado del Servicio | `GET` | `/api/v1/formularioNeumatico` | **`/api/v1/formularios/neumaticos/estado`** |
| **Neumáticos** | Listado Paginado de Reportes | `GET` | `/api/v1/reportes` | **`/api/v1/formularios/neumaticos/reportes`** |
| **Neumáticos** | Detalle de Reporte por ID | `GET` | `/api/v1/reportes/{id}` | **`/api/v1/formularios/neumaticos/reportes/{id}`** |
| **Pauta** | Catálogo Maestro (11 Ítems) | `GET` | `/api/v1/mantencion/pauta/items` | **`/api/v1/formularios/pauta/items`** |
| **Pauta** | Consultar Respuestas y Resumen | `GET` | `/api/v1/mantencion/{id}/pauta` | **`/api/v1/formularios/pauta/solicitudes/{id}`** |
| **Pauta** | Guardar Respuestas en Lote | `POST` | `/api/v1/mantencion/{id}/pauta` | **`/api/v1/formularios/pauta/solicitudes/{id}`** |
| **Mantención** | Formulario Ingreso Solicitud | `POST` | `/api/v1/mantencion/solicitudes` | **`/api/v1/formularios/mantencion/solicitudes`** |

---

## 3. Especificación Detallada: Formulario de Neumáticos

### 3.1. Enviar Reporte de Neumático
Permite a cualquier chofer o mecánico reportar un problema de neumáticos desde terreno.

- **Método:** `POST`
- **URL:** `/api/v1/formularios/neumaticos`
- **Content-Type:** `multipart/form-data`
- **Autenticación:** Opcional (Si se envía cabecera `Authorization: Bearer <token>`, el backend asocia automáticamente el `usuario_id`). Si no hay token, se puede pasar `usuario_id` en el formulario.

#### Campos de `FormData`

| Campo | Tipo | Requerido | Descripción |
| --- | --- | :---: | --- |
| `maquina` | `string` | **Sí** | Número identificador del bus o máquina (ej: `"102"`). |
| `ruedas` | `string` | **Sí** | Posición de la rueda (ej: `"1"`, `"delantera_izq"`, o array serializado). |
| `motivo` | `string` | **Sí** | Descripción del defecto (ej: `"Baja presión y desgaste irregular banda exterior"`). |
| `marca_fuego` | `string` | No (Opcional) | Código identificador de marca de fuego (ej: `"MF-9842"`). |
| `evidencia` | `File` (Blob) | No (Opcional) | Fotografía de la rueda o defecto (formatos `.jpg`, `.jpeg`, `.png`, `.webp`). |
| `usuario_id` | `integer` | No | Solo si no se usa token JWT Bearer. |

> ⚠️ **CAMBIOS CRÍTICOS RESPECTO A VERSIONES ANTERIORES:**
> 1. **`precio` / `monto`:** ¡ELIMINADO! Ya no debe enviarse en el formulario.
> 2. **`tipo_bus`:** ¡ELIMINADO del input manual! El backend consulta automáticamente la máquina en la base de datos y resuelve su tipo (`"Doble Piso"`, `"Interurbano"`, etc.).

#### Ejemplo de Petición en JavaScript (Frontend)

```typescript
const formData = new FormData();
formData.append("maquina", "102");
formData.append("ruedas", "delantera_izq");
formData.append("motivo", "Desgaste lateral con alambre a la vista");
formData.append("marca_fuego", "MF-10293"); // Opcional

if (fotoArchivo) {
  formData.append("evidencia", fotoArchivo); // File desde <input type="file">
}

const response = await fetch("http://localhost:8000/api/v1/formularios/neumaticos", {
  method: "POST",
  headers: {
    // Si el usuario está autenticado:
    "Authorization": `Bearer ${token}`
  },
  body: formData
});

const data = await response.json();
```

#### Respuesta Exitosa (`200 OK`)

```json
{
  "status": "success",
  "message": "Formulario recibido correctamente",
  "data": {
    "usuario_id": 1,
    "maquina": "102",
    "tipo_bus": "Doble Piso",
    "ruedas": "delantera_izq",
    "motivo": "Desgaste lateral con alambre a la vista",
    "marca_fuego": "MF-10293",
    "evidencia": "https://storage.googleapis.com/narbus-evidencias/neumaticos/uuid.jpg"
  },
  "received_at": "2026-09-25T14:15:22.981452"
}
```

---

### 3.2. Listar Reportes de Neumáticos Paginados
Diseñado para la pantalla de supervisión y control de neumáticos.

- **Método:** `GET`
- **URL:** `/api/v1/formularios/neumaticos/reportes`
- **Query Parameters:**
  - `page` (`number`, default `1`): Página a consultar (1-indexed).
  - `page_size` (`number`, default `20`, máx `100`): Registros por página.
  - `n_bus` (`string`, opcional): Filtro por número de máquina/bus (ej: `?n_bus=102`).
- **Cabeceras de Respuesta HTTP:**
  - `X-Total-Count`: Cantidad total de registros encontrados.

#### Respuesta Exitosa (`200 OK`)

```json
{
  "total": 35,
  "page": 1,
  "page_size": 20,
  "total_pages": 2,
  "items": [
    {
      "id": 1,
      "usuario_id": 1,
      "maquina": "102",
      "tipo_bus": "Doble Piso",
      "ruedas": "delantera_izq",
      "motivo": "Desgaste lateral con alambre a la vista",
      "marca_fuego": "MF-10293",
      "evidencia_url": "https://storage.googleapis.com/narbus-evidencias/neumaticos/uuid.jpg",
      "created_at": "2026-09-25T14:15:22"
    }
  ]
}
```

---

## 4. Especificación Detallada: Formulario de Pauta Preventiva

### 4.1. Catálogo Maestro de Pauta (11 Ítems)
Retorna la lista ordenada de ítems oficiales a inspeccionar en maestranza.

- **Método:** `GET`
- **URL:** `/api/v1/formularios/pauta/items`
- **Autenticación:** Requiere `Authorization: Bearer <token>`
- **Cache-Control:** `private, max-age=300, stale-while-revalidate=60`

#### Respuesta Exitosa (`200 OK`)

```json
[
  {
    "id": 1,
    "categoria": "Motor",
    "item": "Nivel y estado de aceite de motor",
    "orden": 1,
    "is_active": true
  },
  {
    "id": 2,
    "categoria": "Frenos",
    "item": "Estado y espesor de pastillas/balatas",
    "orden": 2,
    "is_active": true
  }
]
```

---

### 4.2. Consultar Respuestas y Estado de Pauta de una OT
Consulta el estado de avance, respuestas registradas y si la pauta está completa para una solicitud.

- **Método:** `GET`
- **URL:** `/api/v1/formularios/pauta/solicitudes/{id}`
- **Parámetros de Ruta:** `id` = ID de la solicitud de mantención.
- **Autenticación:** Requiere `Authorization: Bearer <token>`

#### Respuesta Exitosa (`200 OK`)

```json
{
  "total_items": 11,
  "respondidos": 2,
  "pendientes": 9,
  "completado": false,
  "items_con_defecto": 1,
  "respuestas": [
    {
      "id": 501,
      "solicitud_id": 24,
      "item_id": 1,
      "item_categoria": "Motor",
      "item_nombre": "Nivel y estado de aceite de motor",
      "estado": "BUENO",
      "observacion": null,
      "mecanico_id": 2,
      "mecanico_nombre": "Pedro Mecánico",
      "fecha_registro": "2026-09-25T11:00:00"
    },
    {
      "id": 502,
      "solicitud_id": 24,
      "item_id": 2,
      "item_categoria": "Frenos",
      "item_nombre": "Estado y espesor de pastillas/balatas",
      "estado": "DEFECTO",
      "observacion": "Pastillas con desgaste severo",
      "mecanico_id": 2,
      "mecanico_nombre": "Pedro Mecánico",
      "fecha_registro": "2026-09-25T11:05:00"
    }
  ]
}
```

---

### 4.3. Guardar Respuestas de Pauta en Lote (Batch Update)
Permite al mecánico marcar varios o todos los ítems de una sola vez. Es una operación atómica (`ON CONFLICT DO UPDATE`).

- **Método:** `POST`
- **URL:** `/api/v1/formularios/pauta/solicitudes/{id}`
- **Autenticación:** Requiere rol `MECANICO` o `ADMIN`
- **Content-Type:** `application/json`

#### Payload (`PautaBatchUpdateDTO`)

```json
{
  "respuestas": [
    {
      "item_id": 1,
      "estado": "BUENO",
      "observacion": null
    },
    {
      "item_id": 2,
      "estado": "DEFECTO",
      "observacion": "Pastillas con desgaste severo"
    },
    {
      "item_id": 3,
      "estado": "NO_APLICA",
      "observacion": "Sistema no presente en este modelo"
    }
  ]
}
```

> **Valores válidos para `estado`:**
> - `"BUENO"`
> - `"DEFECTO"`
> - `"NO_APLICA"`

#### Respuesta Exitosa (`200 OK`)
Retorna el objeto `PautaEstadoResumenDTO` con los contadores recalculados inmediatamente tras el guardado.

---

## 5. Especificación Detallada: Formulario de Ingreso de Mantención

### 5.1. Crear Solicitud / Ingreso a Maestranza
Formulario utilizado por conductores para reportar fallas antes o al llegar a maestranza, o por supervisores para ingresar un bus directamente.

- **Método:** `POST`
- **URL:** `/api/v1/formularios/mantencion/solicitudes`
- **Autenticación:** Requiere rol `CONDUCTOR`, `SUPERVISOR` o `ADMIN`.
- **Content-Type:** Admite `multipart/form-data` (con fotos) o `application/json` (sin archivos).

#### Opción A: Envío con Fotos (`multipart/form-data`)

```typescript
const formData = new FormData();
formData.append("n_bus", "102"); // Número de máquina
formData.append("descripcion_general", "Ruidos en transmisión y vibración en tren delantero");

// Lista de fallas identificadas
const detalles = [
  {
    falla_id: 1, // ID de la falla de catálogo
    descripcion_personalizada: "Vibración al superar los 80 km/h"
  }
];
formData.append("detalles", JSON.stringify(detalles));

// Fotos adjuntas
fotos.forEach((foto) => {
  formData.append("fotos", foto);
});

const res = await fetch("http://localhost:8000/api/v1/formularios/mantencion/solicitudes", {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${token}`
  },
  body: formData
});
```

#### Opción B: Envío JSON Puro (`application/json`)

```json
{
  "n_bus": "102",
  "descripcion_general": "Ingreso programado para revisión de frenos",
  "detalles": [
    {
      "falla_id": 2,
      "descripcion_personalizada": "Chillido metálico al frenar"
    }
  ]
}
```

#### Respuesta Exitosa (`201 Created`)
Retorna el objeto completo `SolicitudDTO` con la orden de trabajo en estado `"PENDIENTE"`.

---

## 6. Modelos de Datos en TypeScript (Copiar y Pegar en el Frontend)

```typescript
// ==========================================
// 1. NEUMÁTICOS
// ==========================================

export interface FormularioNeumaticoPayload {
  maquina: string;
  ruedas: string;
  motivo: string;
  marca_fuego?: string | null;
  evidencia?: File | Blob | null;
  usuario_id?: number | null;
}

export interface FormularioNeumaticoResponse {
  status: string;
  message: string;
  data: {
    usuario_id?: number | null;
    maquina: string;
    tipo_bus?: string | null;
    ruedas: string;
    motivo: string;
    marca_fuego?: string | null;
    evidencia?: string | null;
  };
  received_at: string;
}

export interface ReporteNeumaticoItem {
  id: number;
  usuario_id?: number | null;
  maquina: string;
  tipo_bus?: string | null;
  ruedas: string;
  motivo: string;
  marca_fuego?: string | null;
  evidencia_url?: string | null;
  created_at: string;
}

export interface ReporteNeumaticoPaginadoResponse {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  items: ReporteNeumaticoItem[];
}

// ==========================================
// 2. PAUTA PREVENTIVA
// ==========================================

export type EstadoItemPauta = "BUENO" | "DEFECTO" | "NO_APLICA";

export interface PautaTallerItem {
  id: number;
  categoria: string;
  item: string;
  orden: number;
  is_active: boolean;
}

export interface PautaRespuesta {
  id?: number | null;
  solicitud_id: number;
  item_id: number;
  item_categoria?: string | null;
  item_nombre?: string | null;
  estado: EstadoItemPauta;
  observacion?: string | null;
  mecanico_id?: number | null;
  mecanico_nombre?: string | null;
  fecha_registro?: string | null;
}

export interface PautaEstadoResumen {
  total_items: number;
  respondidos: number;
  pendientes: number;
  completado: boolean;
  items_con_defecto: number;
  respuestas: PautaRespuesta[];
}

export interface PautaRespuestaUpdateItem {
  item_id: number;
  estado: EstadoItemPauta;
  observacion?: string | null;
}

export interface PautaBatchUpdatePayload {
  respuestas: PautaRespuestaUpdateItem[];
}
```

---

## 7. Manejo Centralizado de Errores

Todos los endpoints retornan errores estándar en formato JSON:

| Código HTTP | Significado | Estructura de Respuesta |
| :---: | --- | --- |
| `400 Bad Request` | Regla de negocio infringida o parámetro inválido | `{"detail": "Mensaje explicativo del error"}` |
| `401 Unauthorized` | Token ausente o expirado | `{"detail": "No autenticado"}` |
| `403 Forbidden` | Rol insuficiente para la operación | `{"detail": "Se requiere rol de MECANICO o ADMIN"}` |
| `404 Not Found` | Solicitud, bus o ítem no encontrado | `{"detail": "Solicitud de taller no encontrada"}` |
| `422 Unprocessable` | Validación de tipos Pydantic fallida | `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` |
