# Auditoría de Flujos, Cantidad de Consultas y Latencia a 8.800 km

**Fecha:** 2026-09-09  
**Módulos Auditados:** Auth, Buses, Mantención, Neumáticos, Supervisión, Core  
**Entorno de Análisis:** Python 3.12, FastAPI, SQLAlchemy 2.0 Async, PostgreSQL (Neon Cloud us-east-2 Ohio)  
**Distancia Backend-BD:** ~8.800 km (Chile a EE.UU. Costa Este / Ohio)  
**RTT Base de Red:** ~140 ms a 160 ms por viaje  

---

## 1. Contexto Físico y Modelo de Red

Para 8.800 km a través de cables submarinos de fibra óptica transcontinentales:
* **Velocidad de señal en fibra:** $\approx 204.000\text{ km/s}$ ($4,9\,\mu\text{s/km}$).
* **RTT mínimo de red:** $\approx 140\text{ ms} - 150\text{ ms}$.
* **Regla:** En este escenario, el tiempo de cálculo del motor SQL en Neon ($2 - 8\text{ ms}$) es irrelevante frente al tiempo de tránsito de red ($140\text{ ms}$). Cada consulta SQL secuencial añade un retraso directo de $\sim 140\text{ ms}$ al usuario.

---

## 2. Inventario de Flujos por Módulo

### 2.1. Módulo Auth (`/auth`)
* `POST /login`: **1 consulta** (~150 ms). Óptimo con JOIN `rol`.
* `POST /register`: **4 consultas** (~580 ms). Lookup usuario + lookup rol + INSERT + SELECT (por `db.refresh`).
* `GET /me`: **0 consultas (en caché)** / 1 consulta (miss). `_USER_CACHE` (TTL 5 min) elimina 99% de viajes.
* `GET /mecanicos/buscar`: **2 consultas** (~290 ms). `lazy='selectin'` en rol genera 2do viaje evitable con `joinedload`.
* `GET /usuarios`: **2 consultas** (~290 ms).
* `POST /usuarios`: **4 consultas** (~580 ms).
* `DELETE /usuarios/{id}`: **3 consultas** (~435 ms).

### 2.2. Módulo Buses (`/buses`)
* `GET /buses/buscar`: **1 consulta** (~150 ms). Filtro indexado por prefijo + cabecera `Cache-Control`.
* `GET /buses`: **1 consulta** (~150 ms).
* `GET /buses/{id}` y `/numero/{n_bus}`: **1 consulta** (~150 ms).
* `PATCH /buses/{id}/en-taller`: **3 consultas** (~435 ms).

### 2.3. Módulo Mantención (`/mantencion`)
* `GET /mantencion/pendientes`: **1 consulta** (~160 ms). 1 CTE SQL nativa con `json_agg` (reducido de 5.8s a 0.16s).
* `GET /mantencion/mis-trabajos`: **1 consulta** (~160 ms). 1 CTE SQL nativa con `json_agg`.
* `GET /mantencion/{id}`: **1 consulta** (~170 ms). 1 CTE SQL nativa con `json_agg` (árbol relacional completo).
* `POST /mantencion/solicitudes` (Crear OT):
  - *Optimizado (con bus_id y falla_id):* **1 consulta** (~160 ms). DTO construido en memoria.
  - *Legado:* **3 consultas** (~440 ms).
* `GET /mantencion/categorias`: **2 consultas** (~290 ms).
* `GET /mantencion/pauta/items`: **1 consulta** (~150 ms).
* `GET /mantencion/{id}/pauta`: **4 consultas** (~580 ms).
* `PATCH .../detalles/{id}/check`: **8 consultas** (~1.160 ms). `get_solicitud_operacional` ejecuta 5 viajes de `selectinload`.
* `PATCH .../detalles/{id}/repuesto`: **8 consultas** (~1.160 ms).
* `POST .../tomar`: **10 consultas** (~1.450 ms).
* `POST .../autoasignar`: **10 consultas** (~1.450 ms).
* `POST .../terminar-avance`: **11 consultas** (~1.600 ms).
* `POST .../detalles` (Agregar falla): **10 consultas** (~1.450 ms).
* `POST .../finalizar`: **13 consultas** (~1.880 ms).
* `POST .../pauta` (Batch checklist): **15 consultas** (~2.170 ms). Punto más crítico del módulo.

### 2.4. Módulo Neumáticos (`/neumaticos`)
* `GET /formularioNeumatico`: **0 consultas** (~1 ms).
* `POST /formularioNeumatico`: **2 a 3 consultas** (~290 - 435 ms). I/O de imagen en threadpool (`asyncio.to_thread`).
* `GET /reportes/{id}`: **1 consulta** (~150 ms).

### 2.5. Módulo Supervisión (`/supervision`)
* `GET /supervision/resumen-taller` (KPIs): **8 consultas secuenciales** (~1.160 ms). Ejecuta 8 `await` sucesivos.
* `GET /supervision/alertas`: **3 consultas** (~435 ms).
* `GET /supervision/auditoria/buses-taller`: **6 consultas** (~870 ms). Cascada `selectinload` de trazabilidad.

---

## 3. Matriz de Cuellos de Botella Principales

1. **`get_solicitud_operacional` (5 roundtrips):** Empleado por todas las mutaciones operativas de mecánicos (`check`, `repuesto`, `tomar`, `autoasignar`, `terminar_avance`, `finalizar`). Al usar `selectinload` genera 5 viajes a Neon antes de aplicar la regla de negocio.
2. **`POST /mantencion/{id}/pauta` (15 roundtrips, ~2.17s):** Mayor tiempo de respuesta de la API debido a cargas operacionales, consultas de pauta y reconstrucción del resumen.
3. **`GET /supervision/resumen-taller` (8 roundtrips, ~1.16s):** 8 consultas independientes ejecutadas de forma secuencial en lugar de una consulta analítica unificada o concurrente.
4. **`await db.refresh()` en entidades mutadas (+1 roundtrip por endpoint):** En Auth, Buses y Neumáticos añade 140 ms de latencia evitable.

---

## 4. Próximos Pasos Recomendados

* **Fase 1 (Quick Wins):** Eliminar `db.refresh` y cambiar `lazy='selectin'` por `joinedload` en usuarios/roles.
* **Fase 2 (Mutaciones de Mantención):** Optimizar `get_solicitud_operacional` a 1 sola consulta SQL (reduciendo mutaciones de 1.2s - 1.5s a ~320ms).
* **Fase 3 (Supervisión):** Consolidar las 8 consultas de KPIs en 1 sola consulta con CTEs analíticas (reduciendo de 1.16s a 160ms).
