# Guía Frontend: Resolver Falla Supervisora — Multi-Mecánico

> **AV-0112** | Fecha: 2026-10-02 | Módulo: Supervisión

Esta guía documenta el contrato actualizado del endpoint de resolución de fallas
desde la vista de supervisión, que ahora soporta indicar **uno o varios mecánicos**
que resolvieron la avería.

---

## 1. Cambio Clave

El payload ahora acepta el campo **`mecanicos_ids`** (lista de IDs). El campo
`mecanico_id` singular sigue funcionando para retrocompatibilidad total.

| Campo | Tipo | Descripción |
|---|---|---|
| `mecanico_id` | `number \| null` | Singular, retrocompatible (1 mecánico) |
| `mecanicos_ids` | `number[] \| null` | **Nuevo** — lista de mecánicos resolutores |
| `estado` | `"RESUELTA" \| "INCOMPLETA" \| "PENDIENTE"` | Estado destino |
| `comentario` | `string \| null` | Observación opcional del supervisor |

> **Regla de prioridad:** si se envía `mecanicos_ids`, se ignora `mecanico_id`.
> Si se envía solo `mecanico_id`, funciona exactamente igual que antes.

---

## 2. Tipos TypeScript

```typescript
// DTO de entrada
interface ResolverFallaSupervisionPayload {
  estado?: "RESUELTA" | "INCOMPLETA" | "PENDIENTE";
  resuelto?: boolean;           // Alias legacy, usar estado preferentemente
  mecanico_id?: number;         // Singular, retrocompatible
  mecanicos_ids?: number[];     // NUEVO: multi-seleccion
  motivo_incompleto?: string;
  comentario?: string;
}

// DTO de respuesta (sin cambios de contrato)
interface MecanicoResumenDTO {
  id: number;
  nombre: string;
}

interface DetalleUpdateDTO {
  detalle_id: number;
  solicitud_id: number;
  estado: "RESUELTA" | "INCOMPLETA" | "PENDIENTE";
  resuelto: boolean;
  falta_repuesto: boolean;
  motivo_incompleto?: string;
  mecanico_resolvio_id?: number;          // ID del 1er mecanico (retrocompat)
  mecanico_resolvio_nombre?: string;      // Ej: "Juan Perez, Carlos Gomez"
  mecanicos_resolvieron: MecanicoResumenDTO[];  // Lista completa estructurada
  comentario_repuesto?: string;
  fecha_resolucion?: string;
}
```

---

## 3. Endpoints

```
PATCH /api/v1/supervision/solicitudes/{solicitud_id}/detalles/{detalle_id}/resolver
PATCH /api/v1/supervision/solicitudes/{solicitud_id}/detalles/{detalle_id}/check
```

Ambas rutas son equivalentes y aceptan el mismo payload.

---

## 4. Ejemplos de Payload

### 4.1. Supervisora selecciona 2 mecanicos (NUEVO)

```json
{
  "estado": "RESUELTA",
  "mecanicos_ids": [12, 17],
  "comentario": "Trabajaron juntos en la reparacion del motor"
}
```

**Respuesta:**
```json
{
  "detalle_id": 42,
  "solicitud_id": 8,
  "estado": "RESUELTA",
  "resuelto": true,
  "falta_repuesto": false,
  "mecanico_resolvio_id": 12,
  "mecanico_resolvio_nombre": "Juan Perez, Carlos Gomez",
  "mecanicos_resolvieron": [
    { "id": 12, "nombre": "Juan Perez" },
    { "id": 17, "nombre": "Carlos Gomez" }
  ],
  "fecha_resolucion": "2026-10-02T15:30:00"
}
```

### 4.2. Un solo mecanico (retrocompatible — ambas formas son equivalentes)

```json
{ "estado": "RESUELTA", "mecanico_id": 12 }
```
```json
{ "estado": "RESUELTA", "mecanicos_ids": [12] }
```

### 4.3. Marcar como INCOMPLETA

```json
{
  "estado": "INCOMPLETA",
  "motivo_incompleto": "Falta el repuesto original"
}
```

### 4.4. Reabrir (PENDIENTE)

```json
{
  "estado": "PENDIENTE",
  "comentario": "Se revisara nuevamente manana"
}
```

---

## 5. Ejemplo de llamada fetch/axios

```typescript
async function resolverFallaConMecanicos(
  solicitudId: number,
  detalleId: number,
  mecanicosIds: number[],
  comentario?: string
): Promise<DetalleUpdateDTO> {
  const payload: ResolverFallaSupervisionPayload = {
    estado: "RESUELTA",
    mecanicos_ids: mecanicosIds,
    comentario: comentario,
  };

  const response = await fetch(
    `/api/v1/supervision/solicitudes/${solicitudId}/detalles/${detalleId}/resolver`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail ?? "Error al resolver la falla");
  }

  return response.json();
}
```

---

## 6. Modal del Supervisor — Logica recomendada

```tsx
// Estado del componente
const [mecanicosSeleccionados, setMecanicosSeleccionados] = useState<number[]>([]);

const toggleMecanico = (id: number) => {
  setMecanicosSeleccionados(prev =>
    prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
  );
};

// Renderizar checkboxes con mecanicos disponibles
{mecanicosDisponibles.map((mec) => (
  <label key={mec.id}>
    <input
      type="checkbox"
      checked={mecanicosSeleccionados.includes(mec.id)}
      onChange={() => toggleMecanico(mec.id)}
    />
    {mec.nombre}
  </label>
))}

// Al confirmar
const handleConfirmar = async () => {
  if (mecanicosSeleccionados.length === 0) {
    setError("Debe seleccionar al menos un mecanico");
    return;
  }
  const resultado = await resolverFallaConMecanicos(
    solicitudId,
    detalleId,
    mecanicosSeleccionados,
    comentario
  );
  onFallaResuelta(resultado);
};
```

---

## 7. Renderizado del resultado

Usar `mecanicos_resolvieron` (lista) para badges individuales.
Usar `mecanico_resolvio_nombre` (string) para texto simple:

```tsx
function ResolutoresDisplay({ detalle }: { detalle: SolicitudDetalleDTO }) {
  const { mecanicos_resolvieron, resuelto } = detalle;

  if (!resuelto || mecanicos_resolvieron.length === 0) {
    return <span className="badge-pendiente">Pendiente</span>;
  }

  return (
    <div className="resolutores">
      {mecanicos_resolvieron.length > 1 && (
        <span className="badge-equipo">
          Equipo ({mecanicos_resolvieron.length})
        </span>
      )}
      {mecanicos_resolvieron.map((mec) => (
        <span key={mec.id} className="badge-mecanico">
          {mec.nombre}
        </span>
      ))}
    </div>
  );
}
```

> **Retrocompatibilidad:** Componentes que usan solo `mecanico_resolvio_nombre`
> seguiran mostrando "Juan Perez, Carlos Gomez" sin ningun cambio.

---

## 8. Errores HTTP 422 comunes

| Mensaje del backend | Causa | Solucion en Frontend |
|---|---|---|
| `"Debe indicar al menos un mecanico..."` | RESUELTA sin IDs y sin cuadrilla previa | Requerir seleccion de al menos 1 mecanico |
| `"El mecanico con ID X no existe o no se encuentra activo"` | ID invalido o baja del sistema | Refrescar lista de mecanicos disponibles |
| `"No se pueden modificar fallas de una solicitud finalizada"` | OT en estado FINALIZADO | Deshabilitar edicion para OTs finalizadas |

---

## 9. Endpoints de lectura (sin cambios)

Los siguientes endpoints ya devuelven `mecanicos_resolvieron` en `detalles[]`:

- `GET /api/v1/supervision/solicitudes/{id}`
- `GET /api/v1/taller/solicitudes/{id}`
- `GET /api/v1/taller/solicitudes/pendientes`

**Cero breaking changes** para el frontend existente.
