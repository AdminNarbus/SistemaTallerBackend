# Guía de Integración Frontend: Filtro y Campo de Última Modificación de OT

Esta guía documenta los cambios implementados en la API Backend de Taller (`BackendTallerNarbus`) para permitir el filtrado y ordenamiento de Órdenes de Trabajo (OT) por su **fecha de última modificación** (`fecha_actualizacion`), tanto en la vista del Mecánico como en la vista de Supervisión/Auditoría.

---

## 1. Resumen de Cambios en la API

1. **Nuevo Campo en Modelos y DTOs (`fecha_actualizacion`):**
   - Presente en todos los DTOs de listado (`SolicitudResumenDTO`) y detalle (`SolicitudDTO`).
   - Formato: ISO 8601 UTC (`string`), ej: `"2026-10-01T10:00:00Z"`.
   - Se actualiza automáticamente cada vez que una OT sufre cualquier mutación (toma de trabajo, autoasignación, checks de fallas, solicitud de repuestos, pauta preventiva, bitácora de comentarios, cambio de estado o cierre).

2. **Ordenamiento Predeterminado:**
   - Todas las listas (`/pendientes`, `/mis-trabajos`, `/auditoria/buses-taller`) se ordenan ahora por:
     $$\text{fecha\_actualizacion DESC, id DESC}$$
   - Esto garantiza que las OTs que acaban de tener actividad o novedades aparezcan inmediatamente en las primeras posiciones.

3. **Nuevos Query Parameters para Filtrado:**
   - `fecha_modificacion_desde`: Fecha/hora inicial (inclusive).
   - `fecha_modificacion_hasta`: Fecha/hora final (inclusive).
   - *Aliases compatibles:* `fecha_desde` y `fecha_hasta` también son aceptados de manera intercambiable.

---

## 2. Endpoints Afectados y Parámetros

### A. Vista Mecánico — Pestaña "Buses en Taller" (Pendientes / Reportados)
- **Método y URL:** `GET /api/v1/taller/pendientes`
- **Autenticación:** Requiere Bearer Token (Rol: `MECANICO` o `ADMIN`).
- **Query Parameters:**
  | Parámetro | Tipo | Requerido | Descripción | Ejemplo |
  | :--- | :--- | :---: | :--- | :--- |
  | `fecha_modificacion_desde` | `string` (ISO 8601 / Date) | No | Filtra OTs modificadas desde esta fecha | `2026-10-01` o `2026-10-01T00:00:00Z` |
  | `fecha_modificacion_hasta` | `string` (ISO 8601 / Date) | No | Filtra OTs modificadas hasta esta fecha | `2026-10-01T23:59:59Z` |
  | `skip` | `number` | No | Paginación (default: `0`) | `0` |
  | `limit` | `number` | No | Límite por página (default: `20`, máx: `100`) | `20` |

### B. Vista Mecánico — Pestaña "Mis Trabajos" (Asignadas al Mecánico)
- **Método y URL:** `GET /api/v1/taller/mis-trabajos`
- **Autenticación:** Requiere Bearer Token (Rol: `MECANICO` o `ADMIN`).
- **Query Parameters:** Mismos parámetros (`fecha_modificacion_desde`, `fecha_modificacion_hasta`, `skip`, `limit`).

### C. Vista Supervisión — Pestaña "Auditoría de Buses en Taller"
- **Método y URL:** `GET /api/v1/supervision/auditoria/buses-taller`
- **Autenticación:** Requiere Bearer Token (Rol: `SUPERVISOR` o `ADMIN`).
- **Query Parameters:**
  | Parámetro | Tipo | Requerido | Descripción | Ejemplo |
  | :--- | :--- | :---: | :--- | :--- |
  | `n_bus` | `string` | No | Búsqueda por número de bus | `302` |
  | `estado` | `string` | No | `PENDIENTE`, `EN_REPARACION`, `FINALIZADO`, etc. | `EN_REPARACION` |
  | `mecanico_nombre` | `string` | No | Búsqueda por mecánico asignado | `Juan` |
  | `fecha_modificacion_desde` | `string` | No | Filtra por última modificación desde | `2026-10-01T08:00:00Z` |
  | `fecha_modificacion_hasta` | `string` | No | Filtra por última modificación hasta | `2026-10-01T20:00:00Z` |
  | `skip` | `number` | No | Offset de paginación (default: `0`) | `0` |
  | `limit` | `number` | No | Tamaño de página (default: `20`) | `20` |

---

## 3. Reglas de Formato de Fechas (¡Muy Importante!)

Para evitar errores de validación HTTP 422:

> [!WARNING]
> En cadenas de consulta (query params de URL), el carácter `+` (ej: `+00:00`) se interpreta como espacio si no está codificado con `encodeURIComponent`.
> 
> **Recomendación:**
> - Enviar fechas con sufijo UTC `Z` (formato estándar de `toISOString()`):
>   `new Date().toISOString()` -> `"2026-10-01T13:45:00.000Z"`
> - O enviar solo fecha en formato `YYYY-MM-DD`:
>   `"2026-10-01"` (el backend interpreta inicio del día `00:00:00 UTC`).

---

## 4. Tipos TypeScript Actualizados

Actualizar la interfaz de resumen en el frontend (`ProtoNeumaticos`):

```typescript
// src/types/solicitud.ts o en el archivo de tipos de taller

export interface SolicitudResumenDTO {
  id: number;
  n_bus: string;
  estado: "REPORTADO" | "PENDIENTE" | "EN_REPARACION" | "LIBERADO" | "FINALIZADO";
  chofer?: string | null;
  tiempo_taller?: number | null;
  numero_fallas: number;
  mecanicos?: Array<{
    mecanico_nombre: string;
    is_activo: boolean;
  }>;
  detalles?: Array<{
    id: number;
    nombre: string;
    falla_nombre?: string;
    categoria_nombre?: string;
    descripcion_personalizada?: string;
    resuelto: boolean;
    falta_repuesto: boolean;
  }>;
  fecha_creacion: string;           // ISO 8601
  fecha_actualizacion: string;      // ISO 8601 (NUEVO: fecha última modificación)
  fecha_cierre?: string | null;
  fecha_liberacion?: string | null;
  horas_en_taller?: number | null;
  reincidencias_30d?: number;
  pauta_completada?: boolean;
}
```

---

## 5. Ejemplos de Implementación en React

### A. Servicio API (`solicitudesService.ts`)

```typescript
export interface FiltrosSolicitudesParams {
  skip?: number;
  limit?: number;
  fecha_modificacion_desde?: string;
  fecha_modificacion_hasta?: string;
  n_bus?: string;
  estado?: string;
  mecanico_nombre?: string;
}

export const getPendientes = async (params?: FiltrosSolicitudesParams): Promise<{ data: SolicitudResumenDTO[]; total: number }> => {
  const query = new URLSearchParams();
  if (params?.skip !== undefined) query.set("skip", params.skip.toString());
  if (params?.limit !== undefined) query.set("limit", params.limit.toString());
  if (params?.fecha_modificacion_desde) query.set("fecha_modificacion_desde", params.fecha_modificacion_desde);
  if (params?.fecha_modificacion_hasta) query.set("fecha_modificacion_hasta", params.fecha_modificacion_hasta);

  const res = await api.get(`/api/v1/taller/pendientes?${query.toString()}`);
  const total = Number(res.headers["x-total-count"] || res.data.length);
  return { data: res.data, total };
};

export const getAuditoriaBuses = async (params?: FiltrosSolicitudesParams): Promise<{ data: SolicitudResumenDTO[]; total: number }> => {
  const query = new URLSearchParams();
  if (params?.skip !== undefined) query.set("skip", params.skip.toString());
  if (params?.limit !== undefined) query.set("limit", params.limit.toString());
  if (params?.n_bus) query.set("n_bus", params.n_bus);
  if (params?.estado) query.set("estado", params.estado);
  if (params?.mecanico_nombre) query.set("mecanico_nombre", params.mecanico_nombre);
  if (params?.fecha_modificacion_desde) query.set("fecha_modificacion_desde", params.fecha_modificacion_desde);
  if (params?.fecha_modificacion_hasta) query.set("fecha_modificacion_hasta", params.fecha_modificacion_hasta);

  const res = await api.get(`/api/v1/supervision/auditoria/buses-taller?${query.toString()}`);
  const total = Number(res.headers["x-total-count"] || res.data.length);
  return { data: res.data, total };
};
```

### B. Componente de Filtro Rápido en `DashboardMecanico.tsx` o `AuditoriaTab.tsx`

```tsx
import React, { useState } from "react";

interface FiltroFechaProps {
  onFiltrar: (desde?: string, hasta?: string) => void;
}

export const FiltroFechaUltimaModificacion: React.FC<FiltroFechaProps> = ({ onFiltrar }) => {
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");

  const handleAplicar = () => {
    // Si se envía fecha sin hora, convertir a ISO inicio y fin de día
    const desdeIso = fechaDesde ? `${fechaDesde}T00:00:00Z` : undefined;
    const hastaIso = fechaHasta ? `${fechaHasta}T23:59:59Z` : undefined;
    onFiltrar(desdeIso, hastaIso);
  };

  const handleLimpiar = () => {
    setFechaDesde("");
    setFechaHasta("");
    onFiltrar(undefined, undefined);
  };

  const setFiltroHoy = () => {
    const hoy = new Date().toISOString().split("T")[0];
    setFechaDesde(hoy);
    setFechaHasta(hoy);
    onFiltrar(`${hoy}T00:00:00Z`, `${hoy}T23:59:59Z`);
  };

  const setFiltroUltimos7Dias = () => {
    const ahora = new Date();
    const hace7d = new Date();
    hace7d.setDate(ahora.getDate() - 7);

    const desdeStr = hace7d.toISOString().split("T")[0];
    const hastaStr = ahora.toISOString().split("T")[0];

    setFechaDesde(desdeStr);
    setFechaHasta(hastaStr);
    onFiltrar(`${desdeStr}T00:00:00Z`, `${hastaStr}T23:59:59Z`);
  };

  return (
    <div className="flex flex-wrap items-center gap-2 bg-slate-50 dark:bg-slate-800/60 p-2.5 rounded-lg border border-slate-200 dark:border-slate-700 text-xs">
      <span className="font-semibold text-slate-700 dark:text-slate-300">Modificado:</span>
      
      {/* Botones de presets rápidos */}
      <button
        type="button"
        onClick={setFiltroHoy}
        className="px-2.5 py-1 bg-white dark:bg-slate-700 border rounded hover:bg-slate-100 dark:hover:bg-slate-600 transition"
      >
        Hoy
      </button>
      <button
        type="button"
        onClick={setFiltroUltimos7Dias}
        className="px-2.5 py-1 bg-white dark:bg-slate-700 border rounded hover:bg-slate-100 dark:hover:bg-slate-600 transition"
      >
        Últimos 7 días
      </button>

      {/* Datepickers manuales */}
      <div className="flex items-center gap-1.5 ml-2">
        <label className="text-slate-500">Desde:</label>
        <input
          type="date"
          value={fechaDesde}
          onChange={(e) => setFechaDesde(e.target.value)}
          className="border rounded px-2 py-0.5 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200"
        />
        <label className="text-slate-500">Hasta:</label>
        <input
          type="date"
          value={fechaHasta}
          onChange={(e) => setFechaHasta(e.target.value)}
          className="border rounded px-2 py-0.5 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200"
        />
        <button
          type="button"
          onClick={handleAplicar}
          className="px-3 py-1 bg-amber-600 text-white font-medium rounded hover:bg-amber-700 transition"
        >
          Filtrar
        </button>
        {(fechaDesde || fechaHasta) && (
          <button
            type="button"
            onClick={handleLimpiar}
            className="px-2 py-1 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 transition"
          >
            Limpiar
          </button>
        )}
      </div>
    </div>
  );
};
```

### C. Visualización de "Última Modificación" en las Tarjetas/Filas de la OT

Para mostrar cuándo fue la última actividad de una OT de forma amigable (ej: "Hace 15 min" o "Hoy 14:30"):

```tsx
import { formatDistanceToNow, format } from "date-fns";
import { es } from "date-fns/locale";

export const BadgeUltimaModificacion = ({ fecha }: { fecha?: string }) => {
  if (!fecha) return null;

  const dateObj = new Date(fecha);
  const textoRelativo = formatDistanceToNow(dateObj, { addSuffix: true, locale: es });
  const textoExacto = format(dateObj, "dd/MM/yyyy HH:mm");

  return (
    <span
      title={`Modificado: ${textoExacto}`}
      className="inline-flex items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800/80 px-2 py-0.5 rounded-full"
    >
      <svg className="w-3 h-3 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      Modificado {textoRelativo}
    </span>
  );
};
```
