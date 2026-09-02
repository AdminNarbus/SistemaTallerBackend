# Contratos de API para Frontend: Sistema Integral de Taller Narbus

> **Documento de Integración Frontend-Backend**  
> **Versión:** 2.0.0  
> **Fecha:** 2026-09-02  
> **Rama Backend:** `feature/sistema-integral-taller-y-pauta`  
> **Estado:** Implementado, verificado con 43/43 tests y desplegado en local.

---

## 1. Resumen Ejecutivo de Cambios y Nueva Filosofía Operacional

Este documento recopila todos los cambios contractuales (endpoints nuevos, modificados, payloads de entrada, respuestas JSON y códigos de estado) para que el equipo de Frontend pueda actualizar las pantallas del sistema de Taller Narbus.

### Principales Transformaciones:
1. **Co-responsabilidad Atómica por Falla (Sin Líder Único Piramidal):**
   - Cada mecánico ya no "toma el bus completo", sino que se asigna o autoasigna a **fallas específicas** (`detalles_ids`).
   - Si 2 o más mecánicos seleccionan la misma avería, ambos quedan registrados como **co-responsables activos**.
   - Cada mecánico puede entregar su turno o registrar su avance individualmente (`/terminar-avance`), calculándose automáticamente la duración de su trabajo en minutos sin desasignar a los demás.
2. **Filtro Estricto de Flota de Buses:**
   - La flota operativa de buses de taller corresponde exclusivamente al rango `200 <= n_bus < 900`.
   - Buses de auxilio o vehículos de apoyo (`< 200` y `>= 900`) son excluidos por defecto en los endpoints de búsqueda y listado del taller mediante el parámetro `solo_flota_taller=true`.
   - Nuevo flag `en_taller: bool` en el modelo de Bus para control de acceso físico a patios de mantenimiento.
3. **Pauta Preventiva de Taller (19 Ítems Obligatorios):**
   - Catálogo estandarizado de 19 revisiones preventivas categorizadas (Motor, Frenos, Dirección, Luces, Cabina, Carrocería, etc.).
   - Admite estados: `"OK"`, `"DEFECTO"`, `"NO_APLICA"`.
4. **Cierre Condicional y Liberación del Bus:**
   - Para liberar el bus (`en_taller = False`) se exige que la pauta esté 100% respondida. Si falta algún ítem, se exige obligatoriamente un `motivo_incompleto_checklist`.
   - Si quedan averías no resueltas o paralizadas por falta de repuestos, se exige obligatoriamente un `motivo_cierre_parcial`.
5. **Centro de Alertas y Telemetría de Supervisión:**
   - Detección automática en tiempo real de averías bloqueadas por falta de repuestos (`REPUESTO_FALTANTE`), defectos críticos en pautas preventivas (`DEFECTO_PAUTA`) y buses en reparación sin mecánicos activos (`BUS_SIN_MECANICOS`).

---

## 2. Formato Estándar de Errores

Todas las excepciones de dominio responden con la siguiente estructura JSON unificada:

```json
{
  "error": {
    "code": "BUSINESS_RULE_VIOLATION | NOT_FOUND | CONFLICT | FORBIDDEN | HTTP_ERROR | VALIDATION_ERROR",
    "message": "Mensaje legible para el usuario o interfaz",
    "detail": null
  }
}
```

- `422 Unprocessable Content`: Violación de regla de negocio (`BUSINESS_RULE_VIOLATION`) o error de schema Pydantic (`VALIDATION_ERROR`).
- `404 Not Found`: Recurso inexistente (`NOT_FOUND`).
- `403 Forbidden`: Usuario autenticado sin permisos de rol suficientes (`FORBIDDEN`).
- `401 Unauthorized`: Token expirado o ausente (`HTTP_ERROR`).

---

## 3. Módulo Buses (`/api/v1/buses`)

### 3.1 `GET /api/v1/buses` (Modificado)
- **Descripción:** Listado paginado de buses con filtro de flota taller por defecto.
- **Query Params:**
  - `solo_flota_taller: bool` (default: `true`). Si es `true`, solo retorna buses con `200 <= n_bus < 900`.
  - `en_taller: Optional[bool]`. Permite filtrar buses que actualmente están o no dentro del taller.
- **Respuesta:** `List[BusBaseDTO]` con el nuevo campo `en_taller: bool`.

### 3.2 `GET /api/v1/buses/buscar` (Modificado)
- **Query Params:**
  - `query: str` (ej: `"30"`)
  - `solo_flota_taller: bool` (default: `true`)
- **Respuesta:** `List[BusAutocompleteDTO]` con `id`, `n_bus`, `patente`, `marca`, `modelo`, `en_taller`.

### 3.3 `PATCH /api/v1/buses/{id}/en-taller` (Nuevo)
- **Roles permitidos:** `SUPERVISOR`, `ADMIN`.
- **Payload:**
```json
{
  "en_taller": true
}
```
- **Respuesta (200 OK):** `BusBaseDTO`.

---

## 4. Módulo Mantención: Asignación Atómica y Avance

### 4.1 `POST /api/v1/mantencion/{id}/autoasignar` (Nuevo)
- **Roles permitidos:** `MECANICO`, `ADMIN`.
- **Descripción:** El mecánico selecciona qué fallas específicas desea reparar. Soporta co-responsabilidad si la falla ya tenía otro mecánico. Pasa el estado a `EN_REPARACION` si estaba `REPORTADO` o `PENDIENTE`.
- **Payload:**
```json
{
  "detalles_ids": [12, 14],
  "comentario": "Iniciando diagnóstico en sistema de frenos"
}
```
- **Respuesta (200 OK):** `SolicitudDTO`.

### 4.2 `POST /api/v1/mantencion/{id}/asignar` (Nuevo)
- **Roles permitidos:** `SUPERVISOR`, `ADMIN`.
- **Descripción:** La supervisora asigna mecánicos a fallas específicas.
- **Payload:**
```json
{
  "mecanico_id": 5,
  "detalles_ids": [12],
  "comentario": "Asignado por turno de la tarde"
}
```
- **Respuesta (200 OK):** `SolicitudDTO`.

### 4.3 `POST /api/v1/mantencion/{id}/terminar-avance` (Nuevo)
- **Roles permitidos:** `MECANICO`, `ADMIN`.
- **Descripción:** El mecánico finaliza su labor en las fallas indicadas. Calcula automáticamente la duración de su asignación en minutos. Si ya no quedan otros mecánicos activos en la solicitud, el estado conmuta automáticamente a `PENDIENTE`.
- **Payload:**
```json
{
  "detalles_ids": [12],
  "comentario": "Se reemplazó manguera flexible, queda pendiente purgado"
}
```
- **Respuesta (200 OK):** `SolicitudDTO`.

---

## 5. Módulo Mantención: Repuestos, Pauta Preventiva y Cierre

### 5.1 `PATCH /api/v1/mantencion/{id}/detalles/{detalle_id}/repuesto` (Nuevo)
- **Roles permitidos:** `MECANICO`, `ADMIN`.
- **Descripción:** Reporta o desmarca si una avería no puede continuar por falta de repuestos. Genera un evento en la bitácora auditable.
- **Payload:**
```json
{
  "falta_repuesto": true,
  "comentario": "Se requiere kit de empaquetaduras y rodamiento cónico"
}
```
- **Respuesta (200 OK):** `SolicitudDTO`.

### 5.2 `GET /api/v1/mantencion/pauta/items` (Nuevo)
- **Roles permitidos:** Todos los usuarios autenticados.
- **Descripción:** Retorna el catálogo maestro de los 19 ítems de inspección preventiva ordenados por categoría y orden numérico.
- **Respuesta (200 OK):**
```json
[
  {
    "id": 1,
    "categoria": "Motor y Transmisión",
    "item": "Nivel y estado de aceite de motor",
    "orden": 1,
    "is_active": true
  },
  {
    "id": 2,
    "categoria": "Frenos y Aire",
    "item": "Presión de tanques y fugas audibles",
    "orden": 2,
    "is_active": true
  }
]
```

### 5.3 `GET /api/v1/mantencion/{id}/pauta` (Nuevo)
- **Roles permitidos:** Todos los usuarios autenticados.
- **Descripción:** Consulta el avance de la pauta preventiva de una orden específica.
- **Respuesta (200 OK):**
```json
{
  "total_items": 19,
  "respondidos": 10,
  "pendientes": 9,
  "completado": false,
  "items_con_defecto": 1,
  "respuestas": [
    {
      "id": 45,
      "solicitud_id": 101,
      "item_id": 1,
      "item_categoria": "Motor y Transmisión",
      "item_nombre": "Nivel y estado de aceite de motor",
      "estado": "OK",
      "observacion": "Nivel correcto en varilla",
      "mecanico_id": 3,
      "mecanico_nombre": "Juan Pérez",
      "fecha_registro": "2026-09-02T14:30:00"
    },
    {
      "id": 46,
      "solicitud_id": 101,
      "item_id": 2,
      "item_categoria": "Frenos y Aire",
      "item_nombre": "Presión de tanques y fugas audibles",
      "estado": "DEFECTO",
      "observacion": "Fuga de aire en pulmón secundario derecho",
      "mecanico_id": 3,
      "mecanico_nombre": "Juan Pérez",
      "fecha_registro": "2026-09-02T14:32:00"
    }
  ]
}
```

### 5.4 `POST /api/v1/mantencion/{id}/pauta` (Nuevo)
- **Roles permitidos:** `MECANICO`, `ADMIN`.
- **Descripción:** Registro o actualización masiva (batch) de respuestas a los ítems de la pauta preventiva.
- **Payload:**
```json
{
  "respuestas": [
    {
      "item_id": 1,
      "estado": "OK",
      "observacion": "Conforme"
    },
    {
      "item_id": 2,
      "estado": "DEFECTO",
      "observacion": "Fuga en racor de acople rápido"
    }
  ]
}
```
- **Respuesta (200 OK):** `PautaEstadoResumenDTO` (mismo schema que 5.3).

### 5.5 `POST /api/v1/mantencion/{id}/liberar` (Nuevo)
- **Roles permitidos:** `MECANICO`, `ADMIN`.
- **Descripción:** Finaliza los trabajos de taller y libera el bus (`bus.en_taller = False`).
- **Reglas de Negocio Validadas:**
  - Si `respondidos < 19`: se **exige** `motivo_incompleto_checklist` obligatorio (HTTP 422 si falta).
  - Si hay fallas con `resuelto == false` o `falta_repuesto == true`: se **exige** `motivo_cierre_parcial` obligatorio (HTTP 422 si falta).
- **Payload:**
```json
{
  "motivo_incompleto_checklist": "Pauta ítems 15-19 no realizada por urgencia de horario de salida",
  "motivo_cierre_parcial": "Falla #2 de aire postergada por repuesto importado en tránsito",
  "comentario_cierre": "Bus operativo para circuito local diurno",
  "liberar_bus_taller": true
}
```
- **Respuesta (200 OK):** `SolicitudDTO` con estado `FINALIZADO` y fecha de cierre.

---

## 6. Módulo Supervisión: KPIs y Alertas

### 6.1 `GET /api/v1/supervision/resumen-taller` (Modificado)
- **Roles permitidos:** `SUPERVISOR`, `ADMIN`.
- **Campos Nuevos en Respuesta:**
```json
{
  "fecha_generacion": "2026-09-02T16:50:00",
  "metricas_estado": {
    "total_solicitudes": 28,
    "reportadas": 4,
    "pendientes": 5,
    "en_reparacion": 7,
    "pendiente_reasignacion": 2,
    "finalizadas": 10,
    "buses_fisicamente_en_taller": 8,
    "fallas_bloqueadas_por_repuesto": 3
  },
  "porcentaje_resolucion_fallas": 65.5,
  "total_fallas_registradas": 60,
  "total_fallas_resueltas": 38,
  "fallas_por_categoria": [
    { "categoria_id": 1, "categoria_nombre": "Frenos y Aire", "total_fallas": 22 },
    { "categoria_id": 2, "categoria_nombre": "Motor y Transmisión", "total_fallas": 18 }
  ],
  "buses_activos_taller": ["204", "302", "501"],
  "alertas": [
    {
      "tipo": "REPUESTO_FALTANTE",
      "severidad": "ALTA",
      "solicitud_id": 12,
      "n_bus": "302",
      "detalle_id": 34,
      "mensaje": "Falla #34 en Bus 302 detenida por falta de repuestos: Se requiere kit de compresor Knorr",
      "fecha_deteccion": "2026-09-02T15:20:00"
    }
  ]
}
```

### 6.2 `GET /api/v1/supervision/alertas` (Nuevo)
- **Roles permitidos:** `SUPERVISOR`, `ADMIN`.
- **Descripción:** Retorna exclusivamente las alertas operacionales activas en tiempo real.
- **Tipos de Alerta:**
  - `REPUESTO_FALTANTE` (`severidad: "ALTA"`): Falla activa con falta de repuestos.
  - `DEFECTO_PAUTA` (`severidad: "MEDIA"`): Ítems marcados con defecto en la pauta preventiva activa.
  - `BUS_SIN_MECANICOS` (`severidad: "MEDIA"`): Órdenes en estado `EN_REPARACION` que no tienen mecánicos activos asignados.
- **Respuesta (200 OK):** `List[AlertaSupervisionDTO]`.

---

## 7. Schema Completo de Referencia: `SolicitudDTO`

El objeto `SolicitudDTO` recibido en todas las respuestas de mantención contiene ahora los siguientes campos clave:

```typescript
interface SolicitudDTO {
  id: number;
  n_bus: string;
  bus_id: number | null;
  bus_patente: string | null;
  usuario_creador_id: number;
  usuario_creador_nombre: string | null;
  mecanico_cierre_id: number | null;
  mecanico_cierre_nombre: string | null;
  estado: "REPORTADO" | "PENDIENTE" | "EN_REPARACION" | "PENDIENTE_REASIGNACION" | "FINALIZADO";
  descripcion_general: string | null;
  foto_url: string | null;
  motivo_incompleto_checklist: string | null; // Justificación si pauta < 19
  motivo_cierre_parcial: string | null;       // Justificación si fallas pendientes
  fecha_creacion: string;
  fecha_cierre: string | null;
  
  // Contadores y flags calculados
  pauta_completada: boolean;
  total_fallas: number;
  fallas_resueltas: number;
  fallas_con_falta_repuesto: number;

  // Listas hijas completas
  detalles: SolicitudDetalleDTO[];
  mecanicos: SolicitudMecanicoDTO[];
  comentarios: SolicitudComentarioDTO[];
  pauta_respuestas: PautaRespuestaDTO[];
}

interface SolicitudDetalleDTO {
  id: number;
  solicitud_id: number;
  falla_id: number | null;
  falla: FallaTallerDTO | null;
  descripcion_personalizada: string | null;
  resuelto: boolean;
  mecanico_resolvio_id: number | null;
  mecanico_resolvio_nombre: string | null;
  falta_repuesto: boolean;
  comentario_repuesto: string | null;
  fecha_creacion: string;
  fecha_resolucion: string | null;
  mecanicos_asignados: MecanicoAsignadoDTO[];      // Mecánicos actualmente trabajando en esta falla
  historial_asignaciones: AsignacionFallaDTO[];   // Historial completo con duración_minutos
}

interface MecanicoAsignadoDTO {
  id: number;
  nombre: string;
  origen: "AUTOASIGNADO" | "SUPERVISOR";
  asignado_por_id: number | null;
  asignado_por_nombre: string | null;
  fecha_asignacion: string;
}

interface PautaRespuestaDTO {
  id: number;
  solicitud_id: number;
  item_id: number;
  item_categoria: string | null;
  item_nombre: string | null;
  estado: "OK" | "DEFECTO" | "NO_APLICA";
  observacion: string | null;
  mecanico_id: number;
  mecanico_nombre: string | null;
  fecha_registro: string;
}
```

---

## 8. Recomendaciones de Implementación para Frontend

1. **Pestaña de Asignación de Mecánico:**
   - Mostrar lista de fallas con casillas de verificación individuales para que el mecánico marque cuáles toma (`POST /{id}/autoasignar`).
   - Mostrar insignias (chips) con los avatares/nombres de los mecánicos co-responsables sobre cada falla.
   - Botón *"Entregar Mi Avance"* por cada falla o selección de fallas (`POST /{id}/terminar-avance`).
2. **Pestaña de Pauta Preventiva:**
   - Renderizar los 19 ítems agrupados por acordeón de categoría.
   - Proveer botones rápidos de selección (`OK` verde, `DEFECTO` ámbar/rojo, `N/A` gris) y campo de texto para observaciones.
   - Barra de progreso de completitud (`respondidos / total_items`).
3. **Modal de Cierre / Liberación:**
   - Si la barra de progreso de pauta no está al 100%, desplegar de forma visible y obligatoria el campo `"Motivo de pauta incompleta"`.
   - Si hay fallas pendientes o con falta de repuestos, desplegar el campo `"Motivo de cierre parcial"`.
4. **Dashboard de Supervisión:**
   - Tarjetas destacadas con `Buses en Taller` y `Fallas Bloqueadas por Repuesto`.
   - Bandeja flotante de `Alertas Activas` con badges de severidad (Rojo = Alta, Amarillo = Media).

---

## 9. Módulo de Reportes de Neumáticos

- **Ruta Activa / Oficial:** `POST /api/v1/formularioNeumatico` (Consumido por el cliente Frontend vía `multipart/form-data`).
- **Ruta Alias Semántica:** `POST /api/v1/neumaticos/reportes` (Ruta RESTful canónica documentada para nuevas integraciones).
- **Payload:**
  - `usuario_id` (int, opcional)
  - `maquina` (string, opcional, n_bus del vehículo)
  - `tipo_bus` (string, opcional)
  - `ruedas` (string JSON, opcional, array de posiciones)
  - `motivo` (string, opcional)
  - `precio` (string, opcional)
  - `marca_fuego` (string, opcional)
  - `evidencia` (UploadFile, opcional, evidencia fotográfica)
- **Respuesta:**
  ```typescript
  interface ReporteNeumaticoResponse {
    status: "success";
    message: string;
    reporte_id: number | null;
    bus_id: number | null;
    resumen: string;
    datos_recibidos: Record<string, any>;
  }
  ```
