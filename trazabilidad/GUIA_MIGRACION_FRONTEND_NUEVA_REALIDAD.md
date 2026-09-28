# Guía de Migración e Integración Frontend: Nueva Realidad del Backend Narbus

> **Documento Oficial para Desarrolladores Frontend**  
> **Versión de la API:** `v1`  
> **Estado de Compatibilidad:** Sin retrocompatibilidad legacy. Se adopta la arquitectura RESTful limpia y estandarizada.

---

## 1. Resumen Ejecutivo del Cambio

El backend ha reorganizado su arquitectura para eliminar la sobrecarga y el acoplamiento que existían entre el reporte inicial y el trabajo interno del taller.

### Principales Transformaciones:
1. **Nuevo Módulo Centralizado `formularios` (`/api/v1/formularios`):**
   - Agrupa en un único lugar las 3 compuertas de reporte y checklists de flota:
     - **Formulario de Neumáticos** (`/neumaticos`)
     - **Checklist de Pauta Preventiva de 11 ítems** (`/pauta`)
     - **Formulario de Ingreso de Taller / Orden de Trabajo** (`/taller/solicitudes`)
2. **Nuevo Módulo Canónico `taller` (`/api/v1/taller` reemplaza a `/api/v1/mantencion`):**
   - Gestiona exclusivamente la operativa física de la maestranza (cuadrillas, asignaciones atómicas de fallas, averías, cronómetro de estadías, repuestos y finalización).
   - Todos los endpoints de maestranza migran del prefijo `/api/v1/mantencion` al prefijo canónico `/api/v1/taller`, logrando coherencia semántica total con la base de datos (`taller_solicitudes`, etc.) y Clean Architecture.
3. **Eliminación Definitiva del Módulo `neumaticos`:**
   - La carpeta y rutas antiguas `/api/v1/formularioNeumatico` y `/api/v1/reportes` han sido purgadas.
   - Se simplificó el formulario: **se eliminó el campo `precio` / `monto`** y **se eliminó la selección manual de `tipo_bus`** (el backend lo resuelve automáticamente por catálogo de flota). La `marca_fuego` permanece como opcional.

---

## 2. Mapa General de URLs (Antiguo vs. Nuevo)

### A. Módulo Formularios de Entrada (`/api/v1/formularios`)

| Módulo / Funcionalidad | Método HTTP | URL Anterior (Obsoleta/Eliminada) | **Nueva URL Oficial** |
| :--- | :---: | :--- | :--- |
| **Neumáticos - Envío de Formulario** | `POST` | `/api/v1/formularioNeumatico` | **`/api/v1/formularios/neumaticos`** |
| **Neumáticos - Estado de Disponibilidad** | `GET` | `/api/v1/formularioNeumatico` | **`/api/v1/formularios/neumaticos/estado`** |
| **Neumáticos - Listado Paginado de Reportes** | `GET` | `/api/v1/reportes` | **`/api/v1/formularios/neumaticos/reportes`** |
| **Neumáticos - Detalle de Reporte por ID** | `GET` | `/api/v1/reportes/{id}` | **`/api/v1/formularios/neumaticos/reportes/{id}`** |
| **Pauta - Catálogo Maestro (11 Ítems)** | `GET` | `/api/v1/mantencion/pauta/items` | **`/api/v1/formularios/pauta/items`** |
| **Pauta - Consultar Estado y Respuestas OT** | `GET` | `/api/v1/mantencion/{id}/pauta` | **`/api/v1/formularios/pauta/solicitudes/{id}`** |
| **Pauta - Guardado Atómico en Lote** | `POST` | `/api/v1/mantencion/{id}/pauta` | **`/api/v1/formularios/pauta/solicitudes/{id}`** |
| **Taller - Formulario de Ingreso / OT** | `POST` | `/api/v1/mantencion/solicitudes` | **`/api/v1/formularios/taller/solicitudes`** |

### B. Módulo Operativa de Taller / Maestranza (`/api/v1/taller`)

| Operación de Taller | Método HTTP | URL Anterior (Obsoleta) | **Nueva URL Oficial** |
| :--- | :---: | :--- | :--- |
| **Bandeja de Pendientes Taller** | `GET` | `/api/v1/mantencion/pendientes` | **`/api/v1/taller/pendientes`** |
| **Bandeja Mis Trabajos (Mecánico)** | `GET` | `/api/v1/mantencion/mis-trabajos` | **`/api/v1/taller/mis-trabajos`** |
| **Detalle Completo de Solicitud/OT** | `GET` | `/api/v1/mantencion/{id}` | **`/api/v1/taller/{id}`** |
| **Tomar Trabajo (Iniciar Atención)** | `POST` | `/api/v1/mantencion/{id}/tomar` | **`/api/v1/taller/{id}/tomar`** |
| **Autoasignar Falla(s)** | `POST` | `/api/v1/mantencion/{id}/autoasignar` | **`/api/v1/taller/{id}/autoasignar`** |
| **Check de Falla Resuelta** | `PATCH` | `/api/v1/mantencion/{id}/detalles/{detalle_id}/check` | **`/api/v1/taller/{id}/detalles/{detalle_id}/check`** |
| **Reportar Falta de Repuesto** | `PATCH` | `/api/v1/mantencion/{id}/detalles/{detalle_id}/repuesto` | **`/api/v1/taller/{id}/detalles/{detalle_id}/repuesto`** |
| **Añadir Avería Detectada en Taller** | `POST` | `/api/v1/mantencion/{id}/detalles` | **`/api/v1/taller/{id}/detalles`** |
| **Cerrar Avance / Turno de Falla** | `POST` | `/api/v1/mantencion/{id}/terminar-avance` | **`/api/v1/taller/{id}/terminar-avance`** |
| **Liberar Turno de Cuadrilla** | `POST` | `/api/v1/mantencion/{id}/liberar-turno` | **`/api/v1/taller/{id}/liberar-turno`** |
| **Agregar Colaborador a Falla** | `POST` | `/api/v1/mantencion/{id}/colaboradores` | **`/api/v1/taller/{id}/colaboradores`** |
| **Desasignar Mecánico de Falla** | `POST` | `/api/v1/mantencion/{id}/desasignar` | **`/api/v1/taller/{id}/desasignar`** |
| **Agregar Comentario a Bitácora** | `POST` | `/api/v1/mantencion/{id}/comentarios` | **`/api/v1/taller/{id}/comentarios`** |
| **Finalizar Orden de Trabajo** | `POST` | `/api/v1/mantencion/{id}/finalizar` | **`/api/v1/taller/{id}/finalizar`** |
| **Liberar Bus a Ruta (Pausa Taller)** | `POST` | `/api/v1/mantencion/{id}/liberar` | **`/api/v1/taller/{id}/liberar`** |
| **Catálogo de Categorías de Falla** | `GET` | `/api/v1/mantencion/categorias` | **`/api/v1/taller/categorias`** |
| **Catálogo de Fallas de Taller** | `GET` | `/api/v1/mantencion/fallas` | **`/api/v1/taller/fallas`** |

---

## 3. Especificación Técnica de Endpoints

### 3.1. Formulario de Neumáticos

#### A. Enviar Reporte de Neumáticos
* **URL:** `POST /api/v1/formularios/neumaticos`
* **Content-Type:** `multipart/form-data`
* **Autenticación:** Opcional. Si el usuario está autenticado, enviar `Authorization: Bearer <token>` para que el backend asocie automáticamente el `usuario_id`. Si no se dispone de token, enviar `usuario_id` en el cuerpo del formulario.
* **Payload (`FormData`):**

| Parámetro | Tipo | Requerido | Descripción |
| :--- | :--- | :---: | :--- |
| `maquina` | `string` | **Sí** | Número identificador del bus o máquina (ej: `"102"`, `"BUS-505"`). |
| `ruedas` | `string` | **Sí** | Posición de la rueda afectada (ej: `"delantera_izq"`, `"1"` o JSON string). |
| `motivo` | `string` | **Sí** | Descripción del desgaste o problema observado. |
| `marca_fuego` | `string` | No (Opcional) | Código identificador de marca de fuego (ej: `"MF-9842"`). |
| `evidencia` | `File` (Blob) | No (Opcional) | Archivo de fotografía (`image/jpeg`, `image/png`, `image/webp`, máx 10 MB). |
| `usuario_id` | `integer` | No | ID del usuario si no viaja en token JWT. |

> ⚠️ **NO ENVIAR:**
> - `precio` o `monto` (campo removido del modelo y backend).
> - `tipo_bus` (el backend lo asocia automáticamente desde la flota si la máquina existe).

* **Respuesta Exitosa (`200 OK`):**
```json
{
  "status": "success",
  "message": "Formulario recibido correctamente",
  "data": {
    "usuario_id": 1,
    "maquina": "102",
    "tipo_bus": "Doble Piso",
    "ruedas": "delantera_izq",
    "motivo": "Desgaste irregular en hombro exterior",
    "marca_fuego": "MF-9842",
    "evidencia": "https://storage.googleapis.com/narbus-bucket/solicitudes/uuid.jpg"
  },
  "received_at": "2026-09-25T15:20:00.123456"
}
```

* **Respuestas de Error:**
  - `400 Bad Request`: `{"detail": "Tamaño de imagen excede el límite de 10 MB"}`
  - `422 Unprocessable Content`: Faltan campos requeridos en el `FormData`.

---

#### B. Consultar Estado del Servicio de Neumáticos
* **URL:** `GET /api/v1/formularios/neumaticos/estado`
* **Autenticación:** Pública (no requiere token).
* **Respuesta Exitosa (`200 OK`):**
```json
{
  "status": "success",
  "message": "Servicio de formulario de neumáticos activo y disponible"
}
```

---

#### C. Listado Paginado de Reportes de Neumáticos
* **URL:** `GET /api/v1/formularios/neumaticos/reportes`
* **Autenticación:** Requiere token Bearer (Supervisión, Taller o Administración).
* **Query Parameters:**
  - `page` (`integer`, default `1`): Número de página (1-based).
  - `page_size` (`integer`, default `20`, máx `100`): Registros por página.
  - `n_bus` (`string`, opcional): Filtro por número de máquina/bus (ej: `?n_bus=102`).
* **Cabecera HTTP de Respuesta:**
  - `X-Total-Count`: Total general de reportes registrados (para construir la paginación).
* **Respuesta Exitosa (`200 OK`):**
```json
{
  "total": 42,
  "page": 1,
  "page_size": 20,
  "total_pages": 3,
  "items": [
    {
      "id": 15,
      "usuario_id": 4,
      "maquina": "102",
      "tipo_bus": "Doble Piso",
      "ruedas": "delantera_izq",
      "motivo": "Desgaste irregular en hombro exterior",
      "marca_fuego": "MF-9842",
      "evidencia_url": "https://storage.googleapis.com/.../uuid.jpg",
      "created_at": "2026-09-25T15:20:00"
    }
  ]
}
```

---

#### D. Detalle de Reporte Individual
* **URL:** `GET /api/v1/formularios/neumaticos/reportes/{id}`
* **Autenticación:** Requiere token Bearer.
* **Respuesta Exitosa (`200 OK`):** Retorna el objeto `ReporteNeumaticoResponseDTO`.
* **Respuesta de Error (`404 Not Found`):** `{"detail": "Reporte de neumático con ID 99 no encontrado"}`

---

### 3.2. Formulario y Checklist de Pauta Preventiva (11 Ítems)

#### A. Catálogo Maestro de Pauta
* **URL:** `GET /api/v1/formularios/pauta/items`
* **Autenticación:** Requiere `Authorization: Bearer <token>`.
* **Cache-Control:** `private, max-age=300, stale-while-revalidate=60`
* **Respuesta Exitosa (`200 OK`):**
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

#### B. Consultar Estado y Respuestas de Pauta para una OT
* **URL:** `GET /api/v1/formularios/pauta/solicitudes/{id}`
* **Parámetro de Ruta:** `id` = ID de la solicitud de mantención.
* **Autenticación:** Requiere `Authorization: Bearer <token>`.
* **Respuesta Exitosa (`200 OK`):**
```json
{
  "total_items": 11,
  "respondidos": 2,
  "pendientes": 9,
  "completado": false,
  "items_con_defecto": 1,
  "respuestas": [
    {
      "id": 81,
      "solicitud_id": 12,
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
      "id": 82,
      "solicitud_id": 12,
      "item_id": 2,
      "item_categoria": "Frenos",
      "item_nombre": "Estado y espesor de pastillas/balatas",
      "estado": "DEFECTO",
      "observacion": "Pastillas desgastadas al 90%",
      "mecanico_id": 2,
      "mecanico_nombre": "Pedro Mecánico",
      "fecha_registro": "2026-09-25T11:05:00"
    }
  ]
}
```

---

#### C. Guardar o Actualizar Respuestas de Pauta en Lote (Batch Update)
* **URL:** `POST /api/v1/formularios/pauta/solicitudes/{id}`
* **Autenticación:** Requiere rol `MECANICO` o `ADMIN`.
* **Content-Type:** `application/json`
* **Payload:**
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
      "observacion": "Requiere cambio urgente de pastillas"
    },
    {
      "item_id": 3,
      "estado": "NO_APLICA",
      "observacion": "Bus no cuenta con este componente"
    }
  ]
}
```
* **Estados Permitidos:** `"BUENO"`, `"DEFECTO"`, `"NO_APLICA"`.
* **Respuesta Exitosa (`200 OK`):** Retorna inmediatamente el objeto `PautaEstadoResumenDTO` con los contadores recalculados tras la persistencia atómica.

---

### 3.3. Formulario de Ingreso de Taller / Creación de OT

#### A. Enviar Solicitud de Ingreso a Maestranza
* **URL:** `POST /api/v1/formularios/taller/solicitudes`
* **Autenticación:** Requiere rol `CONDUCTOR`, `SUPERVISOR` o `ADMIN`.
* **Content-Type:** 
  - `multipart/form-data` si se adjuntan fotos de la cámara o galería.
  - `application/json` si se envían datos puros sin archivos binarios.

#### Modalidad 1: Con Fotos (`multipart/form-data`)
```typescript
const formData = new FormData();
formData.append("n_bus", "102");
formData.append("descripcion_general", "Vibración severa en el eje delantero al frenar");

// Fallas específicas identificadas (array JSON string)
const detalles = [
  {
    falla_id: 2,
    descripcion_personalizada: "Disco delantero con surcos profundos"
  }
];
formData.append("detalles", JSON.stringify(detalles));

// Subir una o varias evidencias fotográficas
fotosArray.forEach((foto) => {
  formData.append("fotos", foto);
});
```

#### Modalidad 2: Sin Fotos (`application/json`)
```json
{
  "n_bus": "102",
  "descripcion_general": "Revisión programada de kilometraje",
  "detalles": [
    {
      "falla_id": 1,
      "descripcion_personalizada": "Revisión de niveles y filtros"
    }
  ]
}
```

* **Respuesta Exitosa (`201 Created`):**
Retorna el objeto `SolicitudDTO` con la nueva Orden de Trabajo inicializada en estado `"PENDIENTE"`.

---

### 3.4. Operativa de Averías: Resolución de Fallas (Check Detalle)

#### A. Marcar o Desmarcar Avería Resuelta
* **URL:** `PATCH /api/v1/taller/{id}/detalles/{detalle_id}/check`
* **Autenticación:** Requiere rol `MECANICO`, `SUPERVISOR` o `ADMIN`.
* **Content-Type:** `application/json` (o vía Query Params alternativos)
* **Payload JSON Oficial (`CheckFallaDTO` / `ResolverFallaSupervisoraDTO`):**
```json
{
  "resuelto": true,
  "mecanico_id": 4,
  "comentario": "Freno purgado y balatas calibradas"
}
```
* **Campos del Payload:**
  - `resuelto` (`boolean`, default: `true`): `true` para marcar la falla como resuelta, `false` para desmarcarla.
  - `mecanico_id` (`number`, opcional): ID del mecánico resolutor (clave si la supervisora o jefe de taller marca la resolución a nombre de un mecánico). Si se omite, toma la identidad del usuario autenticado en el token JWT.
  - `comentario` (`string`, opcional): Nota explicativa del trabajo efectuado.
* **Respuesta Exitosa (`200 OK` - `DetalleUpdateDTO` ultraligero de 0 RTTs adicionales):**
```json
{
  "id": 15,
  "resuelto": true,
  "falta_repuesto": false,
  "mecanico_resolvio_id": 4,
  "mecanico_resolvio_nombre": "Carlos Mecánico",
  "fecha_resolucion": "2026-09-25T15:20:00"
}
```

---

## 4. Tipos TypeScript Universales (Copiar y Pegar en el Frontend)

Crea el archivo `src/types/formularios.ts` en tu proyecto de frontend con las siguientes definiciones:

```typescript
// ============================================================
// 1. DOMINIO FORMULARIO DE NEUMÁTICOS
// ============================================================

export interface EnviarFormularioNeumaticoPayload {
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

// ============================================================
// 2. DOMINIO CHECKLIST DE PAUTA PREVENTIVA
// ============================================================

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

// ============================================================
// 3. DOMINIO INGRESO DE MANTENCIÓN / SOLICITUD
// ============================================================

export interface DetalleFallaIngreso {
  falla_id: number;
  descripcion_personalizada?: string | null;
}

export interface FormularioMantencionPayload {
  n_bus: string;
  bus_id?: number | null;
  descripcion_general?: string | null;
  detalles?: DetalleFallaIngreso[] | null;
  fotos?: File[];
}

// ============================================================
// 4. DOMINIO RESOLUCIÓN DE AVERÍAS (CHECK FALLA)
// ============================================================

export interface CheckFallaPayload {
  resuelto?: boolean;
  mecanico_id?: number | null;
  mecanico_resolvio_id?: number | null;
  comentario?: string | null;
}

export interface DetalleUpdateResponse {
  id: number;
  resuelto: boolean;
  falta_repuesto: boolean;
  mecanico_resolvio_id?: number | null;
  mecanico_resolvio_nombre?: string | null;
  fecha_resolucion?: string | null;
}
```

---

## 5. Módulo de Servicios de Frontend (Ejemplo de Implementación con Axios o Fetch)

Guarda este cliente en `src/services/formulariosService.ts`:

```typescript
import axios from "axios";
import {
  EnviarFormularioNeumaticoPayload,
  FormularioNeumaticoResponse,
  ReporteNeumaticoPaginadoResponse,
  PautaTallerItem,
  PautaEstadoResumen,
  PautaBatchUpdatePayload,
  FormularioMantencionPayload,
} from "../types/formularios";

const API_BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000/api/v1";

const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/formularios`,
});

// Interceptor para agregar token JWT si está disponible
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const formulariosService = {
  // ------------------------------------------------------------
  // NEUMÁTICOS
  // ------------------------------------------------------------
  async enviarReporteNeumatico(
    payload: EnviarFormularioNeumaticoPayload
  ): Promise<FormularioNeumaticoResponse> {
    const formData = new FormData();
    formData.append("maquina", payload.maquina);
    formData.append("ruedas", payload.ruedas);
    formData.append("motivo", payload.motivo);
    if (payload.marca_fuego) formData.append("marca_fuego", payload.marca_fuego);
    if (payload.usuario_id) formData.append("usuario_id", payload.usuario_id.toString());
    if (payload.evidencia) formData.append("evidencia", payload.evidencia);

    const { data } = await apiClient.post<FormularioNeumaticoResponse>(
      "/neumaticos",
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    );
    return data;
  },

  async obtenerEstadoNeumaticos(): Promise<{ status: string; message: string }> {
    const { data } = await apiClient.get("/neumaticos/estado");
    return data;
  },

  async listarReportesNeumaticos(
    page = 1,
    pageSize = 20,
    nBus?: string
  ): Promise<ReporteNeumaticoPaginadoResponse> {
    const params: Record<string, any> = { page, page_size: pageSize };
    if (nBus) params.n_bus = nBus;

    const { data } = await apiClient.get<ReporteNeumaticoPaginadoResponse>(
      "/neumaticos/reportes",
      { params }
    );
    return data;
  },

  // ------------------------------------------------------------
  // PAUTA PREVENTIVA
  // ------------------------------------------------------------
  async obtenerItemsPauta(): Promise<PautaTallerItem[]> {
    const { data } = await apiClient.get<PautaTallerItem[]>("/pauta/items");
    return data;
  },

  async obtenerResumenPauta(solicitudId: number): Promise<PautaEstadoResumen> {
    const { data } = await apiClient.get<PautaEstadoResumen>(
      `/pauta/solicitudes/${solicitudId}`
    );
    return data;
  },

  async guardarRespuestasPauta(
    solicitudId: number,
    payload: PautaBatchUpdatePayload
  ): Promise<PautaEstadoResumen> {
    const { data } = await apiClient.post<PautaEstadoResumen>(
      `/pauta/solicitudes/${solicitudId}`,
      payload
    );
    return data;
  },

  // ------------------------------------------------------------
  // INGRESO DE MANTENCIÓN
  // ------------------------------------------------------------
  async crearSolicitudIngreso(payload: FormularioMantencionPayload): Promise<any> {
    const formData = new FormData();
    formData.append("n_bus", payload.n_bus);
    if (payload.bus_id) formData.append("bus_id", payload.bus_id.toString());
    if (payload.descripcion_general)
      formData.append("descripcion_general", payload.descripcion_general);
    if (payload.detalles && payload.detalles.length > 0) {
      formData.append("detalles", JSON.stringify(payload.detalles));
    }
    if (payload.fotos) {
      payload.fotos.forEach((f) => formData.append("fotos", f));
    }

    const { data } = await apiClient.post("/formularios/taller/solicitudes", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  // ------------------------------------------------------------
  // OPERATIVA DE AVERÍAS (CHECK FALLA)
  // ------------------------------------------------------------
  async checkFallaDetalle(
    solicitudId: number,
    detalleId: number,
    payload: CheckFallaPayload = { resuelto: true }
  ): Promise<DetalleUpdateResponse> {
    const { data } = await apiClient.patch<DetalleUpdateResponse>(
      `/taller/${solicitudId}/detalles/${detalleId}/check`,
      payload
    );
    return data;
  },
};
```

---

## 6. Lista de Verificación (Checklist) para el Frontend

- [ ] **Actualizar URL base de Neumáticos:** Cambiar `POST /formularioNeumatico` por `POST /api/v1/formularios/neumaticos`.
- [ ] **Limpiar campos en Formulario de Neumáticos:**
  - [ ] Eliminar input/selector de precio o monto.
  - [ ] Eliminar input/selector manual de `tipo_bus`.
  - [ ] Confirmar que `marca_fuego` sea opcional.
- [ ] **Migrar pantalla de Supervisión de Neumáticos:**
  - [ ] Cambiar llamada `GET /reportes` por `GET /api/v1/formularios/neumaticos/reportes`.
  - [ ] Usar cabecera `X-Total-Count` para paginar de a 20 registros.
- [ ] **Actualizar Checklist de Pauta:**
  - [ ] Obtener los 11 ítems desde `GET /api/v1/formularios/pauta/items`.
  - [ ] Consultar estado de pauta desde `GET /api/v1/formularios/pauta/solicitudes/{id}`.
  - [ ] Guardar respuestas en lote con `POST /api/v1/formularios/pauta/solicitudes/{id}` enviando el array `respuestas`.
- [ ] **Actualizar Creación de Solicitudes:**
  - [ ] Apuntar formulario de ingreso a `POST /api/v1/formularios/taller/solicitudes`.
- [ ] **Actualizar Módulo Maestranza / Taller:**
  - [ ] Reemplazar prefijo `/api/v1/mantencion/*` por `/api/v1/taller/*` en todas las pantallas de mecánicos y supervisores.
