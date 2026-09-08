# Guía Técnica de Integración para el Frontend: Módulo de Mecánicos de Taller

## 1. Contexto de Red y Principios de Rendimiento

El backend de Narbus Taller se ejecuta comunicándose con la base de datos PostgreSQL en la nube de Neon (Región US-East Ohio, ~8.815 km de distancia física con Chile). Cada consulta SQL adicional o petición HTTP redundante agrega una penalización de latencia física de ida y vuelta (RTT) de **~140 ms a ~400 ms**.

Para lograr una experiencia de usuario instantánea y fluida ("Zero-Lag UX") en las tabletas y computadores de los mecánicos en el taller, el Backend ha sido optimizado con los siguientes principios:

1. **Listados Ultrarrápidos en 1 Sola Consulta SQL (Single-Roundtrip CTE + json_agg):** Las vistas de listado (`/pendientes` y `/mis-trabajos`) se ejecutan en **exactamente 1 consulta SQL nativa** en la base de datos de Neon. PostgreSQL genera directamente el JSON consolidado de detalles y mecánicos en ~1.1 ms en el servidor, eliminando de raíz las cascadas de roundtrips secuenciales y reduciendo la latencia de ~5 segundos a < 0.9s en frío y ~0.16s en caliente.
2. **DTO Dedicado de Listado (`SolicitudResumenDTO`):** Los endpoints devuelven `List[SolicitudResumenDTO]`. Este DTO hereda directamente de `SolicitudDTO`, por lo que **no requiere ningún cambio destructivo en el Frontend**: mantiene todas las propiedades necesarias para las tarjetas (`id`, `n_bus`, `bus_patente`, `estado`, `detalles`, `total_fallas`, `mecanicos`, etc.) con arreglos vacíos `[]` en campos pesados como `comentarios` y `pauta_respuestas`.
3. **Caché HTTP con Revalidación en Segundo Plano:** Los endpoints de lectura implementan la cabecera estándar:
   ```http
   Cache-Control: private, max-age=15, stale-while-revalidate=30
   ```
4. **Respuesta en Memoria Libre de Re-consultas (Zero-Query Return):** Cada acción o mutación del mecánico (`tomar`, `autoasignar`, `check`, `repuesto`, `agregar-falla`, `liberar-turno`, `finalizar`) **actualiza el estado en memoria y devuelve directamente el `SolicitudDTO` consolidado**.
5. **Regla de Oro para el Frontend:** Tras realizar una mutación (`POST` o `PATCH`), el frontend **NO debe volver a solicitar la OT mediante `GET /{id}`**. Debe actualizar directamente la caché del cliente (TanStack Query / SWR / Redux / Pinia) con el objeto devuelto por la mutación.

---

## 2. Las 3 Vistas Principales del Mecánico

### Vista 1: "Buses en Taller / Bandeja de Pendientes"
* **Propósito:** Mostrar los buses que han ingresado al taller y requieren atención o reasignación de turno.
* **Método y Ruta:** `GET /api/v1/mantencion/pendientes`
* **Parámetros Query Soportados:**
  * `limit` *(opcional, entero, default `50`)*: Cantidad máxima de solicitudes a recuperar para paginación o scroll infinito.
* **Estados retornados:** `REPORTADO`, `PENDIENTE`, `PENDIENTE_REASIGNACION`.
* **Payload de Respuesta:** Lista de `SolicitudDTO`:
  ```json
  [
    {
      "id": 42,
      "n_bus": "330",
      "bus_id": 15,
      "bus_patente": "KLSW-89",
      "estado": "PENDIENTE",
      "descripcion_general": "Fuga de aire en eje trasero",
      "fecha_creacion": "2026-09-08T14:30:00",
      "total_fallas": 2,
      "fallas_resueltas": 0,
      "fallas_con_falta_repuesto": 0,
      "detalles": [
        {
          "id": 101,
          "solicitud_id": 42,
          "categoria_id": 3,
          "categoria_nombre": "Neumática",
          "descripcion_personalizada": "Pulmón de suspensión pinchado",
          "resuelto": false,
          "falta_repuesto": false,
          "mecanicos_asignados": []
        }
      ],
      "mecanicos": [],
      "comentarios": [],
      "pauta_respuestas": []
    }
  ]
  ```
  > **Nota Clave:** `comentarios` y `pauta_respuestas` vienen como `[]` en esta vista para optimizar el peso del JSON y reducir el tiempo de carga a menos de 50 ms.

---

### Vista 2: "Mis Trabajos Activos / Mi Turno"
* **Propósito:** Mostrar únicamente los trabajos donde el mecánico autenticado está asignado como responsable activo o tiene averías asignadas a su cargo.
* **Método y Ruta:** `GET /api/v1/mantencion/mis-trabajos`
* **Parámetros Query Soportados:**
  * `limit` *(opcional, entero, default `50`)*.
* **Autenticación:** Requiere `Authorization: Bearer <token_mecanico>`.
* **Payload de Respuesta:** Lista de `SolicitudDTO` idéntica a la Vista 1, filtrada por el usuario en sesión.

---

### Vista 3: "Ficha Técnica / Detalle Completo de la OT"
* **Propósito:** Visualización integral de la orden de trabajo, checklist de averías, bitácora histórica inmutable y pauta de mantenimiento.
* **Método y Ruta:** `GET /api/v1/mantencion/{id}`
* **Payload de Respuesta:** Retorna el `SolicitudDTO` completo con **todas las relaciones cargadas en profundidad**:
  ```json
  {
    "id": 42,
    "n_bus": "330",
    "bus_patente": "KLSW-89",
    "estado": "EN_REPARACION",
    "descripcion_general": "Fuga de aire en eje trasero",
    "fecha_creacion": "2026-09-08T14:30:00",
    "total_fallas": 2,
    "fallas_resueltas": 1,
    "fallas_con_falta_repuesto": 0,
    "detalles": [
      {
        "id": 101,
        "categoria_nombre": "Neumática",
        "descripcion_personalizada": "Pulmón de suspensión pinchado",
        "resuelto": false,
        "mecanico_resolvio_nombre": null,
        "falta_repuesto": false,
        "comentario_repuesto": null,
        "mecanicos_asignados": [
          { "id": 2, "nombre": "Pedro Mecánico" }
        ],
        "historial_asignaciones": [
          {
            "id": 201,
            "mecanico_id": 2,
            "mecanico_nombre": "Pedro Mecánico",
            "origen": "AUTOASIGNACION",
            "is_activo": true,
            "duracion_minutos": null
          }
        ]
      }
    ],
    "mecanicos": [
      {
        "id": 301,
        "mecanico_id": 2,
        "mecanico_nombre": "Pedro Mecánico",
        "es_lider_responsable": false,
        "is_activo": true,
        "duracion_minutos": null,
        "fecha_asignacion": "2026-09-08T14:35:00"
      }
    ],
    "comentarios": [
      {
        "id": 501,
        "usuario_nombre": "Pedro Mecánico",
        "tipo": "ASIGNACION",
        "comentario": "Pedro Mecánico inició los trabajos de esta OT atendiendo las fallas: Pulmón de suspensión pinchado",
        "fecha_registro": "2026-09-08T14:35:00"
      }
    ],
    "pauta_respuestas": []
  }
  ```

---

## 3. Acciones del Mecánico y Contratos de Mutación

Todas las mutaciones devuelven el `SolicitudDTO` actualizado inmediatamente en memoria.

### 3.1. Tomar Trabajo General (Co-responsabilidad Horizontal)
* **Método y Ruta:** `POST /api/v1/mantencion/{id}/tomar`
* **Body:**
  ```json
  {
    "colaboradores_ids": [3, 4],
    "comentario_inicial": "Iniciando diagnóstico con equipo de apoyo"
  }
  ```
  *(Tanto `colaboradores_ids` como `comentario_inicial` son opcionales).*
* **Efecto:** Asigna al mecánico en sesión (y colaboradores si los hay), cambia estado a `EN_REPARACION`, registra bitácora y devuelve la OT actualizada.

### 3.2. Autoasignación Atómica de Averías
* **Método y Ruta:** `POST /api/v1/mantencion/{id}/autoasignar`
* **Body:**
  ```json
  {
    "detalles_ids": [101, 102],
    "colaboradores_ids": [3],
    "comentario": "Revisando sistema de frenos y suspensión"
  }
  ```
* **Efecto:** Permite a un mecánico (o grupo) autoasignarse fallas puntuales dentro de una OT comunitaria sin bloquear al resto de mecánicos en otras averías.

### 3.3. Check / Toggle de Reparación de Falla (Checklist Interactivo)
* **Método y Ruta:** `PATCH /api/v1/mantencion/{id}/detalles/{detalle_id}/check`
* **Body:**
  ```json
  {
    "resuelto": true
  }
  ```
* **Regla de Negocio Crítica (Bloqueo Automático):**
  * Si la falla tiene `falta_repuesto === true`, el backend **rechazará la petición con HTTP 400 Bad Request** indicando que no puede resolverse mientras falte repuesto.
  * Al marcar `resuelto: true`, se guarda automáticamente `mecanico_resolvio_id`, `fecha_resolucion` y se genera una entrada en la bitácora.
  * Al marcar `resuelto: false`, la falla se reabre.

### 3.4. Reporte de Falta de Repuesto
* **Método y Ruta:** `POST /api/v1/mantencion/{id}/detalles/{detalle_id}/repuesto`
* **Body:**
  ```json
  {
    "falta_repuesto": true,
    "comentario": "Se requiere pastillas de freno modelo X-200, stock agotado en bodega"
  }
  ```
* **Efecto:** Marca `falta_repuesto: true` en el detalle y agrega una entrada en bitácora visible para supervisores y pañol/adquisiciones.
* **Reanudación / Llegada de Repuesto:** Para desbloquear la falla, enviar `{"falta_repuesto": false, "comentario": "Repuesto recibido de bodega"}`.

### 3.5. Agregar Nueva Avería en Caliente (Detección en Taller)
* **Método y Ruta:** `POST /api/v1/mantencion/{id}/detalles`
* **Body:**
  ```json
  {
    "categoria_id": 2,
    "descripcion_personalizada": "Pastillas desgastadas detectadas al desmontar neumático",
    "autoasignar": true
  }
  ```
* **Efecto:** Agrega inmediatamente una nueva avería a la OT sin necesidad de recargar la página. Si `autoasignar: true`, asigna de inmediato al mecánico ejecutor.

### 3.6. Liberar / Entrega de Turno
* **Método y Ruta:** `POST /api/v1/mantencion/{id}/liberar-turno`
* **Body:**
  ```json
  {
    "comentario": "Turno noche finalizado, falta purgar circuito"
  }
  ```
* **Efecto:** Desasigna a los mecánicos activos, calcula la duración de los trabajos en minutos, cambia el estado a `PENDIENTE_REASIGNACION` y permite que el turno entrante continúe la labor.

### 3.7. Finalizar y Cierre de OT
* **Método y Ruta:** `POST /api/v1/mantencion/{id}/finalizar`
* **Body:**
  ```json
  {
    "liberar_bus_taller": true,
    "comentario_cierre": "Todas las pruebas de ruta aprobadas satisfactoriamente",
    "motivo_cierre_parcial": null,
    "motivo_incompleto_checklist": null
  }
  ```
* **Efecto:**
  * Si todas las fallas están resueltas y `liberar_bus_taller: true`, marca `bus.en_taller = false`.
  * Si hay fallas pendientes, exige obligatoriamente `motivo_cierre_parcial`.
  * Pasa la orden a estado `FINALIZADO`.

---

## 4. Implementación Recomendada en Frontend (React + TanStack Query)

A continuación se detalla la configuración óptima para TanStack Query (React Query) para garantizar máxima velocidad y cero re-consultas innecesarias:

### A. Configuración de Caché en las Consultas (Queries)

```typescript
// hooks/useTallerQueries.ts
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { SolicitudDTO } from '../types/taller';

export const useBusesEnTaller = () => {
  return useQuery({
    queryKey: ['mantencion', 'pendientes'],
    queryFn: async () => {
      const { data } = await axios.get<SolicitudDTO[]>('/api/v1/mantencion/pendientes?limit=50');
      return data;
    },
    staleTime: 15_000,      // Datos frescos por 15 segundos (coincide con max-age=15)
    gcTime: 60_000,         // Mantener en memoria 1 minuto
    refetchInterval: 30_000 // Polling suave cada 30 segundos si la pestaña está activa
  });
};

export const useMisTrabajos = () => {
  return useQuery({
    queryKey: ['mantencion', 'mis-trabajos'],
    queryFn: async () => {
      const { data } = await axios.get<SolicitudDTO[]>('/api/v1/mantencion/mis-trabajos?limit=50');
      return data;
    },
    staleTime: 15_000,
    gcTime: 60_000,
    refetchInterval: 30_000
  });
};

export const useDetalleOT = (solicitudId: number) => {
  return useQuery({
    queryKey: ['mantencion', 'detalle', solicitudId],
    queryFn: async () => {
      const { data } = await axios.get<SolicitudDTO>(`/api/v1/mantencion/${solicitudId}`);
      return data;
    },
    staleTime: 10_000
  });
};
```

---

### B. Mutaciones con Actualización Inmediata en Caché (Zero-Query)

```typescript
// hooks/useTallerMutations.ts
import { useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { SolicitudDTO } from '../types/taller';

export const useCheckFallaMutation = (solicitudId: number) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ detalleId, resuelto }: { detalleId: number; resuelto: boolean }) => {
      const { data } = await axios.patch<SolicitudDTO>(
        `/api/v1/mantencion/${solicitudId}/detalles/${detalleId}/check`,
        { resuelto }
      );
      return data;
    },
    // Actualización optimista instantánea (0 ms perceived latency)
    onMutate: async ({ detalleId, resuelto }) => {
      await queryClient.cancelQueries({ queryKey: ['mantencion', 'detalle', solicitudId] });
      const anterior = queryClient.getQueryData<SolicitudDTO>(['mantencion', 'detalle', solicitudId]);

      if (anterior) {
        queryClient.setQueryData<SolicitudDTO>(['mantencion', 'detalle', solicitudId], {
          ...anterior,
          detalles: anterior.detalles.map((d) =>
            d.id === detalleId ? { ...d, resuelto } : d
          )
        });
      }
      return { anterior };
    },
    // En éxito: usar DIRECTAMENTE la respuesta del backend (evita volver a consultar GET /{id})
    onSuccess: (solicitudActualizada) => {
      queryClient.setQueryData(['mantencion', 'detalle', solicitudId], solicitudActualizada);
      // Opcional: Actualizar el ítem en la lista de pendientes si estuviese visible
      queryClient.setQueryData<SolicitudDTO[]>(['mantencion', 'pendientes'], (prev) =>
        prev?.map((s) => (s.id === solicitudId ? solicitudActualizada : s))
      );
    },
    // Revertir si el backend rechaza (por ejemplo, falta de repuesto)
    onError: (err, variables, context) => {
      if (context?.anterior) {
        queryClient.setQueryData(['mantencion', 'detalle', solicitudId], context.anterior);
      }
    }
  });
};
```

---

## 5. Reglas de Validación y Estados en la UI

| Estado / Condición | Indicador Visual | Acción del Frontend |
| :--- | :--- | :--- |
| `falta_repuesto === true` | Badge Naranja o Rojo "Espera de Repuesto" | **Deshabilitar** el checkbox de "Resuelto". Al hacer hover o clic, mostrar tooltip: *"No se puede resolver hasta recibir el repuesto"*. |
| `resuelto === true` | Badge Verde "Reparado" | Mostrar el nombre del mecánico resolutor (`mecanico_resolvio_nombre`). |
| `is_activo === true` en asignaciones | Avatar o Chip con nombre del mecánico | Muestra quién está trabajando activamente en dicha avería. |
| `estado === 'PENDIENTE_REASIGNACION'` | Badge Ámbar "Turno Entregado" | El botón debe decir *"Continuar Turno"* en lugar de *"Iniciar OT"*. |
| `estado === 'FINALIZADO'` | Badge Gris "OT Finalizada" | Deshabilitar todas las mutaciones y checklists (modo solo lectura). |

---

## 6. Resumen de Beneficios de la Integración

1. **Latencia Percibida = 0 ms:** La UI responde de inmediato con actualización optimista y se sincroniza con el DTO en memoria sin pantallas de carga intermedias.
2. **Cero Consultas Dobles:** El backend nunca es forzado a re-consultar `SELECT` tras un `COMMIT`.
3. **Consistencia de Datos:** La bitácora inmutable y los contadores de fallas resueltas vienen pre-calculados directamente desde el servidor.
