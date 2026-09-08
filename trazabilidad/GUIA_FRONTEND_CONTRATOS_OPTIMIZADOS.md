# Guía Técnica de Integración para el Frontend: Contratos Optimizados de Taller y Buses

## 1. Resumen Ejecutivo
Para reducir drásticamente los tiempos de respuesta y eliminar consultas de búsqueda innecesarias en la base de datos durante la creación de una solicitud de mantenimiento (`POST /api/v1/mantencion/solicitudes`), el Backend ha optimizado los contratos de:
1. **Catálogo de Buses:** Ahora retorna tanto el `id` numérico como el `n_bus` y la `patente`.
2. **Catálogo de Categorías de Avería:** Ahora retorna el `id` de la categoría junto a su `falla_id` predeterminado.
3. **Envío de Solicitud (Chofer):** El formulario del chofer ahora envía directamente el `bus_id` y el `falla_id`, permitiendo al backend persistir la solicitud en **una sola operación atómica** sin consultas intermedias.

---

## 2. Endpoints Modificados y Nuevos Contratos

### A. Búsqueda y Selección de Buses
* **Método y Ruta:** `GET /api/v1/buses/buscar`
* **Parámetros Query:**
  * `query` *(opcional)*: Término o prefijo a buscar (ej: `"33"`).
  * `solo_flota_taller` *(opcional, default `true`)*: Filtra buses en rango operativo (200 a 899).
* **Antes (Deprecado):** Retornaba solo un arreglo plano de cadenas:
  ```json
  [
    "330",
    "331"
  ]
  ```
* **Nuevo Contrato (Recomendado):** Retorna una lista de objetos `BusSimpleDTO`:
  ```json
  [
    {
      "id": 15,
      "n_bus": "330",
      "patente": "KLSW-89",
      "en_taller": false
    },
    {
      "id": 16,
      "n_bus": "331",
      "patente": "KLSW-90",
      "en_taller": false
    }
  ]
  ```

> **Alternativa (Carga Completa al Abrir Formulario):**
> Si el frontend prefiere precargar toda la lista de buses en un desplegable/combobox al iniciar la pantalla, puede seguir usando:
> `GET /api/v1/buses?solo_activos=true&solo_flota_taller=true`
> que ya retorna el listado completo con `id`, `n_bus`, `patente` y marca.

---

### B. Catálogo de Categorías y Fallas de Avería
* **Método y Ruta:** `GET /api/v1/mantencion/categorias`
* **Antes (Deprecado):** Retornaba solo el ID y nombre de la categoría:
  ```json
  [
    {
      "id": 11,
      "nombre": "Frenos",
      "is_active": true
    }
  ]
  ```
* **Nuevo Contrato (Recomendado):** Cada categoría incluye el `falla_id` y `falla_nombre` directamente vinculado:
  ```json
  [
    {
      "id": 11,
      "nombre": "Frenos",
      "is_active": true,
      "falla_id": 11,
      "falla_nombre": "Avería de Frenos"
    },
    {
      "id": 5,
      "nombre": "Motor",
      "is_active": true,
      "falla_id": 5,
      "falla_nombre": "Avería de Motor"
    }
  ]
  ```

---

### C. Creación de Solicitud de Mantención (Formulario Chofer)
* **Método y Ruta:** `POST /api/v1/mantencion/solicitudes`
* **Autenticación:** Header `Authorization: Bearer <TOKEN_JWT_CHOFER>`
* **Nuevo Payload Óptimo (Enviar `bus_id` y `falla_id`):**
  ```json
  {
    "bus_id": 15,
    "n_bus": "330",
    "descripcion_general": "Falla detectada en ruta durante la mañana",
    "foto_url": null,
    "detalles": [
      {
        "falla_id": 11,
        "categoria_id": 11,
        "falla_nombre": "Avería de Frenos",
        "descripcion_personalizada": "Ruidos metálicos al frenar en bajada"
      }
    ]
  }
  ```

* **Respuesta del Servidor (HTTP 201 Created):**
  ```json
  {
    "id": 48,
    "n_bus": "330",
    "bus_id": 15,
    "bus_patente": "KLSW-89",
    "usuario_creador_id": 3,
    "usuario_creador_nombre": "Chofer Juan Perez",
    "mecanico_cierre_id": null,
    "mecanico_cierre_nombre": null,
    "estado": "REPORTADO",
    "descripcion_general": "Falla detectada en ruta durante la mañana",
    "foto_url": null,
    "fecha_creacion": "2026-09-08T13:05:00",
    "total_fallas": 1,
    "fallas_resueltas": 0,
    "detalles": [
      {
        "id": 89,
        "solicitud_id": 48,
        "categoria_id": 11,
        "categoria_nombre": "Frenos",
        "falla_id": 11,
        "falla": {
          "id": 11,
          "categoria_id": 11,
          "nombre": "Avería de Frenos",
          "is_active": true
        },
        "descripcion_personalizada": "Ruidos metálicos al frenar en bajada",
        "resuelto": false
      }
    ]
  }
  ```

---

## 3. Ejemplo de Integración en el Frontend (React / Vue / Angular / Flutter)

### Paso 1: Al cargar el formulario
```javascript
// 1. Cargar categorías con sus fallas
const resCategorias = await api.get('/api/v1/mantencion/categorias');
setCategorias(resCategorias.data); 
// Cada item tiene: { id: 11, nombre: "Frenos", falla_id: 11, falla_nombre: "Avería de Frenos" }

// 2. Al buscar el bus en el Autocomplete / Select
const resBuses = await api.get('/api/v1/buses/buscar?query=33');
setBusesSugeridos(resBuses.data);
// Cada item tiene: { id: 15, n_bus: "330", patente: "KLSW-89" }
```

### Paso 2: Al seleccionar el bus
Guardar el objeto completo del bus seleccionado en el estado local:
```javascript
const [busSeleccionado, setBusSeleccionado] = useState(null); // { id: 15, n_bus: "330", patente: "..." }
```

### Paso 3: Al seleccionar las averías/categorías
```javascript
const agregarFalla = (categoria) => {
  setFallasSeleccionadas([...fallasSeleccionadas, {
    falla_id: categoria.falla_id,
    categoria_id: categoria.id,
    falla_nombre: categoria.falla_nombre,
    descripcion_personalizada: detalleInput
  }]);
};
```

### Paso 4: Al presionar "Enviar Solicitud"
```javascript
const payload = {
  bus_id: busSeleccionado.id,
  n_bus: busSeleccionado.n_bus,
  descripcion_general: descripcionGeneral,
  detalles: fallasSeleccionadas.map(f => ({
    falla_id: f.falla_id,
    categoria_id: f.categoria_id,
    falla_nombre: f.falla_nombre,
    descripcion_personalizada: f.descripcion_personalizada
  }))
};

const response = await api.post('/api/v1/mantencion/solicitudes', payload);
```

---

## 4. Retrocompatibilidad Garantizada
Si el frontend por alguna razón no envía `bus_id` o `falla_id` (versión anterior):
* El backend **sigue funcionando**: buscará el bus por `n_bus` y la falla por `categoria_id`.
* Sin embargo, cuando se envíen `bus_id` y `falla_id` (junto con `falla_nombre`), el tiempo de guardado se reduce en más de un **70%**, pasando de más de 3 segundos a **menos de 800 ms** (0 SELECTs previos, solo 1 COMMIT atómico).

---

## 5. Pautas de Rendimiento y Mitigación de Peticiones Duplicadas

### A. Cabeceras HTTP de Caché en el Navegador (`Cache-Control`)
El backend ahora envía automáticamente cabeceras de caché web en los catálogos:
* `GET /api/v1/buses` y `/buses/buscar`: `Cache-Control: private, max-age=120, stale-while-revalidate=60`
* `GET /api/v1/mantencion/categorias`: `Cache-Control: private, max-age=300, stale-while-revalidate=60`

**Beneficio:** Si el navegador o Axios repite la petición dentro del periodo de 2 a 5 minutos, la respuesta es servida **instantáneamente desde la memoria local del cliente en 0 ms** sin viajar a internet ni contactar a la base de datos.

### B. Evitar Peticiones Duplicadas en el Montaje (React)
En desarrollo, `<React.StrictMode>` ejecuta los `useEffect` dos veces consecutivas. Para evitar disparos redundantes y optimizar la experiencia en producción:

1. **Cargar los catálogos en un Store Global o Context (Zustand, Pinia, Redux):**
   * Cargar la lista de buses y las categorías al iniciar la sesión o al abrir el módulo por primera vez, no en cada render del componente formulario.
2. **Si se utiliza TanStack Query (React Query) o SWR:**
   * Configurar `staleTime: 5 * 60 * 1000` (5 minutos) y `refetchOnWindowFocus: false` para que las listas se mantengan en memoria sin re-dispararse al interactuar con inputs o re-montar pantallas.
3. **Envío de `falla_nombre` en el payload:**
   * Como se muestra en el Paso 3 y 4 del ejemplo de integración, asegurar que el array `detalles` incluya `falla_id` y `falla_nombre`. Esto permite al backend omitir completamente la búsqueda de metadata y persistir la solicitud en menos de 800 ms.

