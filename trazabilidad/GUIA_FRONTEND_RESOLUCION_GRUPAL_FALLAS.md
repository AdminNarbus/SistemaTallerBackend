# Guía de Integración Frontend: Resolución Grupal y Co-responsabilidad de Fallas

Esta guía documenta los cambios implementados en el Backend API (`BackendTallerNarbus`) para soportar la **resolución grupal y co-responsabilidad de fallas en cuadrilla (Opción A)**.

---

## 1. Contexto y Problema Resuelto

### ¿Qué ocurría antes?
Cuando un grupo o cuadrilla de mecánicos trabajaba en una falla y uno de ellos marcaba la falla como realizada (`REALIZADA`) o incompleta (`INCOMPLETA`), el sistema únicamente guardaba el `id` y `nombre` del mecánico individual que ejecutó el clic (`mecanico_resolvio_id`, `mecanico_resolvio_nombre`), dejando invisibles a los compañeros que estaban asignados y colaborando en dicha tarea.

### ¿Cómo funciona ahora (Opción A)?
1. **Co-responsabilidad en tiempo real:** Cuando cualquier integrante de la cuadrilla asignado a la falla la marca como `REALIZADA`:
   - **Todos los mecánicos asignados activamente** a esa falla quedan registrados como resolutores (`resuelto_en_esta_asignacion = true`).
   - El backend devuelve la lista completa de mecánicos en el arreglo `mecanicos_resolvieron: [{ id, nombre }, ...]`.
   - Para **retrocompatibilidad 100%** con componentes existentes, el campo `mecanico_resolvio_nombre` concatena los nombres legibles (ej: `"Juan Pérez, Carlos Gómez"`).
2. **Acciones grupales (Incompleta o Reapertura):**
   - Si la falla se marca como `INCOMPLETA` o se reabre a `PENDIENTE`, todos los mecánicos asignados se limpian de la autoría de resolución (`resuelto_en_esta_asignacion = false`).
3. **Bitácora Inmutable de Auditoría:**
   - La bitácora de la OT registra explícitamente al equipo:
     - `El equipo [Juan Pérez, Carlos Gómez] completó la reparación de la falla...`
     - `El equipo [Juan Pérez, Carlos Gómez] dejó incompleta la reparación...`
     - `El equipo [Juan Pérez, Carlos Gómez] reabrió la falla...`

---

## 2. Tipos y Contratos de Datos (TypeScript)

### 2.1. Nuevo DTO Resumen: `MecanicoResumenDTO`
```typescript
export interface MecanicoResumenDTO {
  id: number;
  nombre: string;
}
```

### 2.2. Modelo de Detalle de Falla (`SolicitudDetalleDTO` y `DetalleUpdateDTO`)
En las respuestas de la OT, cada detalle/falla incluye:

```typescript
export interface SolicitudDetalleDTO {
  id: number;
  falla_id: number;
  falla_descripcion?: string;
  categoria?: string;
  severidad?: string;

  // Estado de la reparación (0: PENDIENTE, 1: REALIZADA, 2: INCOMPLETA)
  estado_reparacion: number;
  is_checked: boolean; // true si estado_reparacion === 1

  // Mecánico individual (el que ejecutó la acción en la UI o líder)
  mecanico_resolvio_id?: number | null;

  // Nombre string concatenado (Retrocompatible para vistas rápidas)
  // Ej: "Juan Pérez, Carlos Gómez" o "Juan Pérez"
  mecanico_resolvio_nombre?: string | null;

  // NUEVO: Arreglo con todos los mecánicos que resolvieron en conjunto
  mecanicos_resolvieron: MecanicoResumenDTO[];

  // Comentarios y metadata
  comentario_mecanico?: string | null;
  comentario_incompleta?: string | null;
  fecha_reparacion?: string | null; // ISO-8601
  asignaciones?: SolicitudAsignacionDTO[];
}
```

---

## 3. Endpoints Afectados

### 3.1. Marcar estado de la falla (Check / Uncheck / Incompleta)
- **Método:** `PATCH`
- **Ruta:** `/api/v1/mantencion/{solicitud_id}/detalles/{detalle_id}/check`
- **Payload (`CheckDetalleDTO`):**
  ```json
  {
    "is_checked": true,
    "estado_reparacion": 1,
    "comentario_mecanico": "Filtros y mangueras reemplazados",
    "comentario_incompleta": null
  }
  ```
- **Respuesta (`DetalleUpdateDTO`):**
  ```json
  {
    "id": 142,
    "is_checked": true,
    "estado_reparacion": 1,
    "mecanico_resolvio_id": 4,
    "mecanico_resolvio_nombre": "Juan Pérez, Carlos Gómez",
    "mecanicos_resolvieron": [
      { "id": 4, "nombre": "Juan Pérez" },
      { "id": 7, "nombre": "Carlos Gómez" }
    ],
    "comentario_mecanico": "Filtros y mangueras reemplazados",
    "comentario_incompleta": null,
    "fecha_reparacion": "2026-10-02T10:15:30Z"
  }
  ```

### 3.2. Consultas de OT (Detalle, Pendientes, Historial)
Los siguientes endpoints incluyen automáticamente los campos `mecanicos_resolvieron` y `mecanico_resolvio_nombre` en cada item del array `detalles`:
- `GET /api/v1/mantencion/{id}`
- `GET /api/v1/mantencion/pendientes`
- `GET /api/v1/mantencion/bus/{bus_id}/activas`

---

## 4. Ejemplos de Implementación en Frontend (React / Tailwind)

### 4.1. Componente para Visualizar Resolutores (Badges / Avatares de Equipo)

```tsx
import React from 'react';
import { SolicitudDetalleDTO } from '@/types/mantencion';

interface ResolutoresFallaProps {
  detalle: SolicitudDetalleDTO;
}

export const ResolutoresFalla: React.FC<ResolutoresFallaProps> = ({ detalle }) => {
  // Solo se muestran resolutores si la falla está REALIZADA (estado_reparacion === 1)
  if (detalle.estado_reparacion !== 1) {
    return null;
  }

  const { mecanicos_resolvieron, mecanico_resolvio_nombre } = detalle;

  // Si existe la lista estructurada con 1 o más mecánicos:
  if (mecanicos_resolvieron && mecanicos_resolvieron.length > 0) {
    const esGrupal = mecanicos_resolvieron.length > 1;

    return (
      <div className="flex flex-wrap items-center gap-1.5 mt-2">
        <span className="text-xs font-medium text-slate-500 mr-1">
          {esGrupal ? 'Resuelto en equipo:' : 'Resuelto por:'}
        </span>
        {mecanicos_resolvieron.map((mec) => (
          <span
            key={mec.id}
            className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-sm"
          >
            <svg
              className="w-3 h-3 mr-1 text-emerald-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
              />
            </svg>
            {mec.nombre}
          </span>
        ))}
      </div>
    );
  }

  // Fallback retrocompatible si solo viene el string mecanico_resolvio_nombre
  if (mecanico_resolvio_nombre) {
    return (
      <div className="text-xs text-emerald-600 font-medium mt-1">
        ✓ Resuelto por: {mecanico_resolvio_nombre}
      </div>
    );
  }

  return null;
};
```

### 4.2. Actualización de Estado Local tras `PATCH check`

Al recibir la respuesta de `PATCH /check`, actualiza la falla en el estado de la OT reemplazando sus propiedades:

```typescript
const handleToggleFalla = async (solicitudId: number, detalleId: number, nuevoEstado: number) => {
  try {
    const payload = {
      is_checked: nuevoEstado === 1,
      estado_reparacion: nuevoEstado,
      comentario_mecanico: nuevoEstado === 1 ? comentario : null,
      comentario_incompleta: nuevoEstado === 2 ? motivoIncompleta : null,
    };

    const response = await api.patch<DetalleUpdateDTO>(
      `/api/v1/mantencion/${solicitudId}/detalles/${detalleId}/check`,
      payload
    );

    const detalleActualizado = response.data;

    // Actualizar la lista en el estado de React / Pinia / Redux
    setSolicitud((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        detalles: prev.detalles.map((d) =>
          d.id === detalleId
            ? {
                ...d,
                is_checked: detalleActualizado.is_checked,
                estado_reparacion: detalleActualizado.estado_reparacion,
                mecanico_resolvio_id: detalleActualizado.mecanico_resolvio_id,
                mecanico_resolvio_nombre: detalleActualizado.mecanico_resolvio_nombre,
                mecanicos_resolvieron: detalleActualizado.mecanicos_resolvieron,
                comentario_mecanico: detalleActualizado.comentario_mecanico,
                comentario_incompleta: detalleActualizado.comentario_incompleta,
                fecha_reparacion: detalleActualizado.fecha_reparacion,
              }
            : d
        ),
      };
    });
  } catch (error) {
    console.error("Error al actualizar estado de la falla:", error);
  }
};
```

---

## 5. Resumen de Ventajas para la Experiencia de Usuario (UI/UX)
1. **Transparencia Total:** Los mecánicos ahora ven sus nombres reconocidos en las fallas que resolvieron conjuntamente, fomentando el trabajo colaborativo en taller.
2. **Cero Cambios Obligatorios si se usa el string:** Las vistas de listado rápido o tablas que usan `{falla.mecanico_resolvio_nombre}` automáticamente mostrarán `"Juan Pérez, Carlos Gómez"` sin necesidad de modificar código.
3. **Capacidad de Desglose:** Las vistas de detalle o fichas de OT pueden iterar `{falla.mecanicos_resolvieron}` para mostrar badges individuales, avatares o filtros por mecánico.
