# Guía Técnica para Frontend: 4 Estados Canónicos de OT y Cronómetro de Taller

Esta guía explica detalladamente la evolución del modelo de estados y telemetría de tiempos en el Backend de Taller Narbus para su integración en la interfaz de usuario (React/Vite).

---

## 1. El Nuevo Flujo de 4 Estados Canónicos

Se elimina el estado intermedio y ficticio `REPORTADO`. Toda Orden de Trabajo (OT) se gestiona a través de **4 estados únicos y universales**:

```
       [ Conductor o Supervisora crea OT ]
                        │
                        ▼
                 [ PENDIENTE ]  <──(Fin de jornada / Entrega de turno)──┐
                        │                                               │
                 (Mecánico toma)                                        │
                        │                                               │
                        ▼                                               │
                [ EN_REPARACION ] ──────────────────────────────────────┘
                        │
                (Cierre parcial)
                        │
                        ▼
                   [ LIBERADO ]  (Bus sale a ruta con fallas pendientes)
                        │
            (Bus vuelve a maestranza)
                        │
                        ▼
                [ EN_REPARACION ]
                        │
           (Todas las fallas resueltas)
                        │
                        ▼
                  [ FINALIZADO ] (OT cerrada definitivamente)
```

### Tabla de Significado y Badges Recomendados en la UI:
| Estado Backend (`estado`) | Significado Operacional | Badge Color Sugerido | Ubicación Física del Bus (`en_taller`) |
| :--- | :--- | :--- | :--- |
| **`PENDIENTE`** | La OT está creada y en espera de atención. Ningún mecánico está trabajando en ella en este minuto (cola de espera o noche/cambio de turno). | Amarillo / Naranja suave (`#F59E0B`) | `true` si el bus ya ingresó a maestranza; `false` si se reportó en ruta. |
| **`EN_REPARACION`** | Hay cuadrilla activa trabajando físicamente sobre el bus con herramientas. | Azul / Celeste activo (`#3B82F6`) | Siempre `true`. |
| **`LIBERADO`** | El bus salió a trabajar a la calle con fallas secundarias o tolerables (cierre parcial). | Morado / Púrpura (`#8B5CF6`) | Siempre `false` (está en ruta). |
| **`FINALIZADO`** | 100% de las fallas fueron resueltas y verificadas. Orden archivada. | Verde esmeralda (`#10B981`) | `false`. |

---

## 2. Diferencia Clave: Estado de la OT vs Ubicación Física (`en_taller`)

En la UI se recomienda no mezclar el estado de la orden con la presencia física del bus:
* **Estado de la Orden (`solicitud.estado`):** Indica la fase de trabajo en que se encuentra la avería (`PENDIENTE`, `EN_REPARACION`, `LIBERADO`, `FINALIZADO`).
* **Presencia Física (`solicitud.bus.en_taller` o `bus.en_taller`):** Booleano que indica si el bus está físicamente dentro del galpón del taller (`true`) o en la calle/terminal (`false`).

> **Ejemplo UI:**
> - Bus 305: Badge de Estado: `PENDIENTE` | Badge de Ubicación: `📍 En Taller (Patio de espera)`
> - Bus 402: Badge de Estado: `LIBERADO` | Badge de Ubicación: `🚌 En Ruta`

---

## 3. Telemetría de Tiempos: Historial de Estadías y Cronómetros con Pausas

### A. Demora al Primer Ingreso (`horas_demora_primer_ingreso`):
* Mide exactamente cuánto tardó el bus desde que el conductor reportó la falla hasta que ingresó físicamente por primera vez al taller:
  $$\text{horas\_demora\_primer\_ingreso} = \text{fecha\_primer\_ingreso\_taller} - \text{fecha\_creacion}$$
* En la UI se puede mostrar como KPI de gestión: *"Tardó 26.5 hrs en llegar a taller desde su reporte"*.

### B. Historial de Estadías / Visitas (`estadias: EstadiaTallerDTO[]`):
Cada vez que el bus entra y sale del taller dentro de la misma OT, el backend genera un registro en el array `estadias`:
```typescript
interface EstadiaTallerDTO {
  numero_visita: number;       // 1, 2, 3...
  fecha_ingreso: string;       // ISO Timestamp
  fecha_salida: string | null; // ISO Timestamp (null si la visita está en curso)
  horas_estadia: number | null;// Horas adentro en esa visita puntual
  motivo_salida: string | null;// "LIBERACION_PARCIAL" | "CIERRE_DEFINITIVO"
}
```
* **En la UI permite mostrar:**
  - **Total de Visitas:** `solicitud.total_visitas` (ej. *"Pasó 2 veces por taller"*).
  - **Detalle de cada visita:**
    - Visita #1: 18.4 hrs (Ingreso: 20-09 08:00 $\rightarrow$ Salida: 21-09 02:24)
    - Visita #2: 6.2 hrs (Ingreso: 23-09 09:00 $\rightarrow$ En curso)
  - **Tiempo Físico Acumulado:** `solicitud.horas_taller_acumuladas` (Suma solo el tiempo adentro del taller, sin contar los días que estuvo trabajando afuera en ruta).

### C. Tiempo Real Liberado en Calle (`fecha_liberacion`):
* Cuando la supervisora o mecánico libera el bus con fallas pendientes:
  - `solicitud.estado = "LIBERADO"`
  - **`bus.en_taller = false`** (físicamente fuera).
  - Se pausa el cronómetro de taller y se estampa `fecha_liberacion = now`.
* **Tiempo que el estado LIBERADO se mantiene activo:**
  ```typescript
  const horasEnRuta = (new Date().getTime() - new Date(solicitud.fecha_liberacion).getTime()) / (1000 * 3600);
  const diasEnRuta = Math.floor(horasEnRuta / 24);
  ```
* Permite al supervisor visualizar la alerta: *"Lleva 4 días liberado en calle con fallas pendientes"*.
* Si el bus reingresa a taller para continuar la reparación, `solicitud.estado` pasa a `EN_REPARACION`, `bus.en_taller = true`, la alerta de liberado se apaga y se abre la Visita #2 en `estadias`.

---

## 4. Cambios en Filtros y Peticiones API

1. **Bandeja de Entrada del Mecánico (`GET /api/v1/mantencion/pendientes`):**
   - Ya no existe el estado `REPORTADO`.
   - Todas las órdenes listas para ser tomadas devuelven `estado: "PENDIENTE"`.
2. **KPIs de Supervisión (`GET /api/v1/supervision/resumen-taller`):**
   - El contador que antes mostraba `reportadas` ahora se unifica en `pendientes`.
   - Se mantiene `buses_fisicamente_en_taller` para saber cuántos vehículos ocupan espacio en el taller en tiempo real.
3. **Cierre de Turno del Mecánico (`POST /api/v1/mantencion/{id}/terminar-avance`):**
   - Cuando todos los mecánicos entregan turno y la orden no tiene cuadrilla activa, la orden regresa a `PENDIENTE` (manteniendo `en_taller: true`).
