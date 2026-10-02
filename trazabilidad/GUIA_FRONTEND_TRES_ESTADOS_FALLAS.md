# Guía de Integración Frontend: Tres Estados de Fallas y Averías (Pendiente, Incompleta, Resuelta)

Esta guía documenta los cambios implementados en la API Backend de Taller (`BackendTallerNarbus`) para soportar **3 estados independientes en cada falla/avería** de una Orden de Trabajo (`TallerSolicitudDetalle`):

$$\text{PENDIENTE} \quad \longleftrightarrow \quad \text{INCOMPLETA} \quad \longleftrightarrow \quad \text{RESUELTA}$$

---

## 1. Resumen de Cambios en la API

1. **Nuevo Campo de Estado (`estado`):**
   - Cada detalle de avería cuenta ahora con un campo `estado` tipado:
     - `"PENDIENTE"`: Falla reportada aún no abordada o reabierta.
     - `"INCOMPLETA"`: Falla con trabajo iniciado o revisada, pero que requiere seguimiento, calibración posterior o continuación en el siguiente turno.
     - `"RESUELTA"`: Falla reparada y concluida exitosamente.
2. **Motivo de Inconclusión (`motivo_incompleto`):**
   - Cuando una falla se marca como `"INCOMPLETA"`, se puede registrar opcionalmente un motivo descriptivo (ej: *"Falta calibración de frenos"*, *"En espera de turno matutino"*, *"Requiere prueba en carretera"*).
   - Si la falla vuelve a `"PENDIENTE"` o pasa a `"RESUELTA"`, el backend limpia automáticamente este motivo.
3. **Métrica en Resumen y Detalle de Solicitud (`fallas_incompletas`):**
   - En `SolicitudDTO` y `SolicitudResumenDTO`, se incluye el conteo:
     - `total_fallas: number`
     - `fallas_resueltas: number`
     - `fallas_incompletas: number` (nuevo)
     - `fallas_pendientes: number`
4. **Reglas de Negocio de Cierre (Finalizar OT):**
   - Para que una OT pueda pasar a estado `"FINALIZADO"` (`POST /solicitudes/{id}/finalizar`), **todas** las fallas deben estar en estado `"RESUELTA"`.
   - Si existen fallas `"PENDIENTE"` o `"INCOMPLETA"`, el backend rechaza la finalización con error HTTP 400 (`BusinessRuleException`).
5. **100% Retrocompatible:**
   - El campo booleano `resuelto` sigue existiendo en todas las respuestas (`resuelto = true` únicamente si `estado == 'RESUELTA'`).
   - El payload del check de falla acepta indistintamente `estado` o el tradicional `resuelto`.

---

## 2. Tipos TypeScript para Frontend

Copiar o actualizar estas definiciones en tu proyecto frontend (ej. `src/types/taller.ts` o `src/types/solicitud.ts`):

```typescript
// 1. Enum de Estados de Falla
export type EstadoFalla = "PENDIENTE" | "INCOMPLETA" | "RESUELTA";

// 2. DTO de Detalle de Falla (Item de Avería)
export interface SolicitudDetalleDTO {
  id: number;
  solicitud_id?: number;
  falla_id?: number | null;
  nombre?: string;
  falla_nombre?: string;
  categoria_nombre?: string;
  descripcion_personalizada?: string | null;
  // --- NUEVOS CAMPOS ---
  estado: EstadoFalla;
  motivo_incompleto?: string | null;
  // --- CAMPO RETROCOMPATIBLE ---
  resuelto: boolean;
  fecha_resolucion?: string | null; // ISO 8601 UTC
  falta_repuesto?: boolean;
}

// 3. Payload para Mutar el Estado de una Falla (PATCH /check)
export interface CheckFallaPayload {
  estado?: EstadoFalla;
  motivo_incompleto?: string | null;
  // Retrocompatibilidad opcional:
  resuelto?: boolean;
}

// 4. Respuesta Inmediata del Backend (DetalleUpdateDTO)
export interface DetalleUpdateDTO {
  id: number;
  solicitud_id: number;
  estado: EstadoFalla;
  motivo_incompleto?: string | null;
  resuelto: boolean;
  fecha_resolucion?: string | null;
  falta_repuesto: boolean;
  mensaje: string;
}

// 5. Métricas de la Orden de Trabajo (SolicitudDTO)
export interface SolicitudDTO {
  id: number;
  n_bus: string;
  estado: "PENDIENTE" | "EN_REPARACION" | "LIBERADO" | "FINALIZADO";
  total_fallas: number;
  fallas_resueltas: number;
  fallas_incompletas: number; // NUEVO
  fallas_pendientes: number;
  detalles: SolicitudDetalleDTO[];
  // ... resto de campos de la OT
}
```

---

## 3. Endpoints y Casos de Uso

### A. Mecánico: Actualizar Estado de una Falla
- **Método y URL:** `PATCH /api/v1/taller/solicitudes/{id}/detalles/{detalle_id}/check`
- **Autenticación:** Bearer Token de Mecánico (o Supervisor/Admin).

#### Caso 1: Marcar Falla como RESUELTA
```json
PATCH /api/v1/taller/solicitudes/15/detalles/42/check
Content-Type: application/json

{
  "estado": "RESUELTA"
}
```
*Respuesta HTTP 200:*
```json
{
  "id": 42,
  "solicitud_id": 15,
  "estado": "RESUELTA",
  "motivo_incompleto": null,
  "resuelto": true,
  "fecha_resolucion": "2026-10-01T15:30:00Z",
  "falta_repuesto": false,
  "mensaje": "Falla marcada como resuelta exitosamente"
}
```

#### Caso 2: Marcar Falla como INCOMPLETA (con motivo opcional)
```json
PATCH /api/v1/taller/solicitudes/15/detalles/42/check
Content-Type: application/json

{
  "estado": "INCOMPLETA",
  "motivo_incompleto": "Falta purgar líquido de frenos en el siguiente turno"
}
```
*Respuesta HTTP 200:*
```json
{
  "id": 42,
  "solicitud_id": 15,
  "estado": "INCOMPLETA",
  "motivo_incompleto": "Falta purgar líquido de frenos en el siguiente turno",
  "resuelto": false,
  "fecha_resolucion": null,
  "falta_repuesto": false,
  "mensaje": "Falla marcada como incompleta"
}
```

#### Caso 3: Reabrir Falla a PENDIENTE
```json
PATCH /api/v1/taller/solicitudes/15/detalles/42/check
Content-Type: application/json

{
  "estado": "PENDIENTE"
}
```
*Respuesta HTTP 200:*
```json
{
  "id": 42,
  "solicitud_id": 15,
  "estado": "PENDIENTE",
  "motivo_incompleto": null,
  "resuelto": false,
  "fecha_resolucion": null,
  "falta_repuesto": false,
  "mensaje": "Falla reabierta a estado pendiente"
}
```

---

### B. Supervisión: Resolver Falla de Supervisión
- **Método y URL:** `PATCH /api/v1/supervision/fallas/{id}/resolver`
- **Autenticación:** Bearer Token de Supervisor.
- **Payload:** Soporta exactamente el mismo esquema:
  ```json
  {
    "estado": "RESUELTA"
  }
  ```
  O para marcar incompleta con motivo:
  ```json
  {
    "estado": "INCOMPLETA",
    "motivo_incompleto": "Revisado por supervisor, requiere ajuste adicional"
  }
  ```

---

## 4. Diseño y Experiencia de Usuario (UI / UX)

### Paleta Visual y Badges Sugeridos

| Estado | Color de Fondo | Color de Texto / Borde | Icono Sugerido | Descripción para el Usuario |
| :--- | :--- | :--- | :---: | :--- |
| **`PENDIENTE`** | `bg-amber-50` / `#FEF3C7` | `text-amber-700` / `#B45309` | ⏳ Reloj / Círculo vacío | Sin iniciar o reabierta |
| **`INCOMPLETA`** | `bg-orange-50` / `#FFEDD5` | `text-orange-700` / `#C2410C` | ⚠️ Pausa / Alerta | En proceso / Incompleta |
| **`RESUELTA`** | `bg-emerald-50` / `#D1FAE5` | `text-emerald-700` / `#047857` | ✅ Check / Listo | Solucionada |

### Patrón de Interacción Recomendado

En la tarjeta o fila de cada falla en la vista de la OT:
1. **Selector de 3 Estados (Segmented Control o Dropdown/Chips):**
   - Permitir al mecánico alternar rápidamente entre **Pendiente**, **Incompleta** y **Resuelta**.
2. **Modal o Diálogo Rápido al Elegir "Incompleta":**
   - Cuando el usuario hace clic en el botón o chip `"Incompleta"`, abrir un modal sencillo:
     - Título: *"Marcar Avería como Incompleta"*
     - Campo de texto (opcional): *"Indica el motivo o trabajo pendiente (ej: falta prueba en ruta, pendiente calibración)"*
     - Botones: `Cancelar` y `Guardar`.
3. **Visualización del Motivo:**
   - Si la falla tiene `estado === "INCOMPLETA"` y `motivo_incompleto`, renderizar una nota pequeña debajo de la descripción:
     ```html
     <div className="mt-1 text-xs text-orange-800 bg-orange-100 p-2 rounded">
       <strong>Motivo de inconclusión:</strong> {falla.motivo_incompleto}
     </div>
     ```
4. **Resumen de la Orden (Cabecera):**
   - Mostrar el desglose claro de avance:
     $$\text{Total: } 4 \quad \mid \quad \text{✅ Resueltas: } 2 \quad \mid \quad \text{⚠️ Incompletas: } 1 \quad \mid \quad \text{⏳ Pendientes: } 1$$
5. **Bloqueo Informativo en el Botón "Finalizar OT":**
   - Si `fallas_pendientes > 0 || fallas_incompletas > 0`, deshabilitar el botón *"Finalizar OT"* o mostrar un tooltip:
     > *"No puedes finalizar la orden mientras existan fallas pendientes o incompletas."*

---

## 5. Ejemplo de Código en React / Axios

### Función de Servicio API (`tallerApi.ts`):

```typescript
import axios from "axios";
import { CheckFallaPayload, DetalleUpdateDTO } from "../types/taller";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000/api/v1";

export async function actualizarEstadoFalla(
  solicitudId: number,
  detalleId: number,
  payload: CheckFallaPayload,
  token: string
): Promise<DetalleUpdateDTO> {
  const response = await axios.patch<DetalleUpdateDTO>(
    `${API_BASE_URL}/taller/solicitudes/${solicitudId}/detalles/${detalleId}/check`,
    payload,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    }
  );
  return response.data;
}
```

### Componente de Fila de Falla (`FallaItem.tsx`):

```tsx
import React, { useState } from "react";
import { EstadoFalla, SolicitudDetalleDTO } from "../types/taller";

interface Props {
  solicitudId: number;
  falla: SolicitudDetalleDTO;
  token: string;
  onActualizado: (detalleActualizado: SolicitudDetalleDTO) => void;
}

export const FallaItem: React.FC<Props> = ({ solicitudId, falla, token, onActualizado }) => {
  const [modalIncompletoAbierto, setModalIncompletoAbierto] = useState(false);
  const [motivo, setMotivo] = useState(falla.motivo_incompleto || "");
  const [cargando, setCargando] = useState(false);

  const cambiarEstado = async (nuevoEstado: EstadoFalla, motivoTexto?: string) => {
    try {
      setCargando(true);
      const res = await actualizarEstadoFalla(
        solicitudId,
        falla.id,
        {
          estado: nuevoEstado,
          motivo_incompleto: nuevoEstado === "INCOMPLETA" ? motivoTexto : undefined,
        },
        token
      );

      onActualizado({
        ...falla,
        estado: res.estado,
        motivo_incompleto: res.motivo_incompleto,
        resuelto: res.resuelto,
        fecha_resolucion: res.fecha_resolucion,
      });
      setModalIncompletoAbierto(false);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Error al actualizar estado de la falla");
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="border p-4 rounded-lg mb-2 shadow-sm bg-white">
      <div className="flex justify-between items-start">
        <div>
          <h4 className="font-semibold text-gray-800">
            {falla.falla_nombre || falla.nombre || falla.descripcion_personalizada || "Avería sin nombre"}
          </h4>
          {falla.categoria_nombre && (
            <span className="text-xs text-gray-500">{falla.categoria_nombre}</span>
          )}
        </div>

        {/* Botones de Selección Rápida de Estado */}
        <div className="flex gap-2">
          <button
            type="button"
            disabled={cargando}
            onClick={() => cambiarEstado("PENDIENTE")}
            className={`px-3 py-1 rounded text-xs font-medium border ${
              falla.estado === "PENDIENTE"
                ? "bg-amber-100 text-amber-800 border-amber-400"
                : "bg-gray-50 text-gray-600 hover:bg-gray-100"
            }`}
          >
            ⏳ Pendiente
          </button>

          <button
            type="button"
            disabled={cargando}
            onClick={() => setModalIncompletoAbierto(true)}
            className={`px-3 py-1 rounded text-xs font-medium border ${
              falla.estado === "INCOMPLETA"
                ? "bg-orange-100 text-orange-800 border-orange-400"
                : "bg-gray-50 text-gray-600 hover:bg-gray-100"
            }`}
          >
            ⚠️ Incompleta
          </button>

          <button
            type="button"
            disabled={cargando}
            onClick={() => cambiarEstado("RESUELTA")}
            className={`px-3 py-1 rounded text-xs font-medium border ${
              falla.estado === "RESUELTA"
                ? "bg-emerald-100 text-emerald-800 border-emerald-400"
                : "bg-gray-50 text-gray-600 hover:bg-gray-100"
            }`}
          >
            ✅ Resuelta
          </button>
        </div>
      </div>

      {/* Nota de Falla Incompleta */}
      {falla.estado === "INCOMPLETA" && falla.motivo_incompleto && (
        <div className="mt-2 text-xs text-orange-900 bg-orange-50 border border-orange-200 p-2 rounded">
          <strong>Pendiente por:</strong> {falla.motivo_incompleto}
        </div>
      )}

      {/* Modal / Diálogo para Ingresar Motivo Incompleto */}
      {modalIncompletoAbierto && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg p-5 max-w-md w-full shadow-lg">
            <h3 className="text-base font-bold text-gray-800 mb-2">
              Marcar Avería como Incompleta
            </h3>
            <p className="text-xs text-gray-600 mb-3">
              Indica qué falta o el motivo por el cual no se pudo concluir en este momento:
            </p>
            <textarea
              className="w-full border rounded p-2 text-sm focus:ring focus:ring-orange-200 outline-none"
              rows={3}
              placeholder="Ej: Faltó calibración de válvulas / Pendiente prueba de ruta mañana..."
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 rounded"
                onClick={() => setModalIncompletoAbierto(false)}
              >
                Cancelar
              </button>
              <button
                type="button"
                className="px-4 py-1.5 text-xs bg-orange-600 hover:bg-orange-700 text-white rounded font-medium"
                onClick={() => cambiarEstado("INCOMPLETA", motivo)}
              >
                Confirmar Incompleta
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
```

---

## 6. Checklist de Implementación para el Frontend

- [ ] Actualizar interfaz `SolicitudDetalleDTO` agregando `estado: EstadoFalla` y `motivo_incompleto?: string | null`.
- [ ] Actualizar interfaz `SolicitudDTO` agregando `fallas_incompletas: number`.
- [ ] Reemplazar el checkbox binario simple por el selector de 3 estados (`PENDIENTE`, `INCOMPLETA`, `RESUELTA`).
- [ ] Implementar ventana modal o input inline para capturar `motivo_incompleto` al seleccionar `INCOMPLETA`.
- [ ] Mostrar badge o alerta de `motivo_incompleto` en la tarjeta de la falla.
- [ ] Incorporar el conteo de fallas incompletas en la barra de progreso de la orden.
- [ ] Validar en la interfaz que el botón "Finalizar OT" informe si existen fallas pendientes o incompletas antes de emitir la petición.
