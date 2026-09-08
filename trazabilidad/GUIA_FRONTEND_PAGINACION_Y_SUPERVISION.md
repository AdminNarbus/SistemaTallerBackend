# Guía Técnica para Frontend: Paginación y Optimización de Supervisión

## 1. Resumen Ejecutivo
Para evitar tiempos de carga prolongados, consumo excesivo de datos móviles en el taller y cuellos de botella por sobrecarga en la base de datos, el Backend ha implementado:
1. **Paginación uniforme con `skip` y `limit`** en las vistas operacionales de mecánicos y en el dashboard de auditoría de supervisión.
2. **Desacoplamiento y aceleración del Centro de Alertas** (`GET /api/v1/supervision/alertas`), que ahora responde en milisegundos consultando únicamente las anomalías activas.
3. **Optimización del Resumen y KPIs de Taller** (`GET /api/v1/supervision/resumen-taller`), procesado mediante agregaciones analíticas directas en SQL.

> [!NOTE]
> **Compatibilidad Garantizada:** Si el Frontend llama a estos endpoints sin enviar `skip` ni `limit`, el backend responderá con los primeros 50 registros (`skip=0`, `limit=50`). No se romperán pantallas existentes.

---

## 2. Endpoints con Paginación (`skip` y `limit`)

Los siguientes tres endpoints ahora aceptan parámetros estándar de paginación por Query String:

| Endpoint | Rol / Acceso | Parámetros Query | Descripción |
| :--- | :--- | :--- | :--- |
| `GET /api/v1/mantencion/pendientes` | Mecánico / Admin | `skip` (default: 0)<br>`limit` (default: 50, max: 100) | Pestaña 1: Buses esperando atención en taller. |
| `GET /api/v1/mantencion/mis-trabajos` | Mecánico / Admin | `skip` (default: 0)<br>`limit` (default: 50, max: 100) | Pestaña 2: Buses asignados activamente al mecánico autenticado. |
| `GET /api/v1/supervision/auditoria/buses-taller` | Supervisor / Admin | `skip` (default: 0)<br>`limit` (default: 50, max: 100)<br>`n_bus`<br>`estado`<br>`mecanico_nombre` | Trazabilidad completa e historial de buses en taller con filtros. |

### Significado de los Parámetros:
* **`skip` (entero $\ge 0$):** Cantidad de registros a omitir desde el inicio.
  * Para la Página 1: `skip = 0`
  * Para la Página 2 (con tamaño 20): `skip = 20`
  * Fórmula general: `skip = (page - 1) * pageSize`
* **`limit` (entero entre 1 y 100):** Cantidad de registros a traer por bloque o página (recomendado en frontend: `10`, `20` o `50`).

---

## 3. Endpoints del Módulo de Supervisión

### A. Centro de Alertas Operacionales
* **Método y Ruta:** `GET /api/v1/supervision/alertas`
* **Autenticación:** Requiere rol `SUPERVISOR` o `ADMIN`.
* **Optimización Realizada:** Antes ejecutaba consultas masivas analíticas innecesarias. Ahora consulta directamente a la base de datos solo las alertas vivas en órdenes no finalizadas.
* **Tipos de Alerta Retornados:**
  1. `REPUESTO_FALTANTE` (Severidad: `ALTA`): Falla pausada por mecánico debido a falta de repuesto.
  2. `DEFECTO_PAUTA` (Severidad: `MEDIA`): Ítem preventivo marcado con defecto en la pauta de 11 puntos.
  3. `BUS_SIN_MECANICOS` (Severidad: `MEDIA`): Bus en estado `EN_REPARACION` que no tiene mecánicos activos asignados.
* **Respuesta (`List[AlertaSupervisionDTO]`):**
  ```json
  [
    {
      "tipo": "REPUESTO_FALTANTE",
      "severidad": "ALTA",
      "solicitud_id": 42,
      "n_bus": "305",
      "detalle_id": 108,
      "mensaje": "Falla #108 en Bus 305 detenida por falta de repuestos: Falta kit compresor Knorr",
      "fecha_deteccion": "2026-09-08T16:30:00"
    }
  ]
  ```

### B. Resumen y KPIs de Taller
* **Método y Ruta:** `GET /api/v1/supervision/resumen-taller`
* **Autenticación:** Requiere rol `SUPERVISOR` o `ADMIN`.
* **Uso Recomendado en Frontend:** Pantalla principal de bienvenida/dashboard del supervisor. Incluye:
  * Desglose de estados de solicitudes (`reportadas`, `pendientes`, `en_reparacion`, `finalizadas`).
  * `buses_fisicamente_en_taller`: conteo físico de buses con `en_taller = True`.
  * `fallas_bloqueadas_por_repuesto`: conteo rápido de fallas detenidas.
  * Porcentaje global de fallas resueltas (`porcentaje_resolucion_fallas`).
  * `fallas_por_categoria`: ranking de averías más frecuentes.
  * `buses_activos_taller`: arreglo con los números de bus con órdenes abiertas.
  * `alertas`: listado de alertas activas en tiempo real.

---

## 4. Ejemplos de Integración en el Frontend

### Ejemplo con Axios / Fetch (Paginación por Botones o Páginas):
```typescript
interface FetchPendientesParams {
  page: number;
  pageSize?: number;
}

export async function getSolicitudesPendientes({ page = 1, pageSize = 20 }: FetchPendientesParams) {
  const skip = (page - 1) * pageSize;
  const response = await api.get('/api/v1/mantencion/pendientes', {
    params: {
      skip,
      limit: pageSize,
    },
  });
  return response.data; // Array de SolicitudResumenDTO
}
```

### Ejemplo con Infinite Scroll (TanStack Query / useInfiniteQuery):
```typescript
import { useInfiniteQuery } from '@tanstack/react-query';

export function useAuditoriaBuses(nBusFiltro?: string) {
  const PAGE_SIZE = 20;

  return useInfiniteQuery({
    queryKey: ['auditoria-buses', nBusFiltro],
    queryFn: async ({ pageParam = 0 }) => {
      const res = await api.get('/api/v1/supervision/auditoria/buses-taller', {
        params: {
          skip: pageParam,
          limit: PAGE_SIZE,
          n_bus: nBusFiltro || undefined,
        },
      });
      return res.data;
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      // Si la última página trajo menos elementos que PAGE_SIZE, no hay más datos
      if (lastPage.length < PAGE_SIZE) return undefined;
      return allPages.length * PAGE_SIZE;
    },
  });
}
```
