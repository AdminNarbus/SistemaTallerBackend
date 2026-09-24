# Guía Frontend: Eliminación de Categorías y Manejo de Averías Directas

Esta guía documenta los cambios arquitectónicos realizados en el backend para **eliminar de raíz el concepto de categorías en las fallas** y operar de forma 100% directa y simple.

---

## 1. El Porqué del Cambio
- **Antes:** Se pretendía clasificar cada avería en una categoría fija (*"Luces"*, *"Frenos"*, *"Motor"*, etc.). Esto obligaba a cargar un catálogo (`GET /categorias`), provocaba categorías vacías, y cuando el usuario escribía un texto libre, en las tablas o auditoría aparecía *"Personalizada / Sin Categoría"* o *"Desconocido"*.
- **Ahora:** En la operación de taller las averías son específicas. El usuario (conductor o mecánico) solo ingresa un texto puntual (ej: *"Freno largo"*, *"Luz quemada derecha"*, *"Fuga de aire"*). No existe distinción entre categoría, nombre o descripción. **La avería se define únicamente por su texto directo**.

---

## 2. Cambios en la Emisión de OT (`POST /api/v1/mantencion/solicitudes`)

### Antes (Payload complejo con categorías e IDs):
```json
{
  "n_bus": "104",
  "detalles": [
    {
      "categoria_id": 1,
      "falla_id": 4,
      "falla_nombre": "Luces",
      "descripcion_personalizada": "Luz quemada"
    }
  ]
}
```

### Ahora (Payload directo y limpio):
Simplemente envías el array de fallas con su `nombre`:
```json
{
  "n_bus": "104",
  "detalles": [
    { "nombre": "Freno largo" },
    { "nombre": "Luz delantera derecha quemada" }
  ]
}
```
> **Nota de Retrocompatibilidad:** Si tu código actual aún envía `falla_nombre` o `descripcion_personalizada`, el backend lo acepta transparentemente y lo mapea sin errores.

### ¿Se debe seguir llamando a `GET /api/v1/mantencion/categorias`?
**No.** Ya no es necesario consumir ese endpoint al abrir el formulario de conductores o supervisión. El paso de "seleccionar categoría" desaparece y el usuario escribe directamente la avería detectada (como ya actualizaste en `FormularioMantencionTaller.tsx`).

---

## 3. Cambios en Respuestas y Listados (`/pendientes`, `/mis-trabajos`, `/auditoria`)

En cualquier endpoint donde se reciban detalles de fallas (`SolicitudDetalleDTO` o `DetalleFallaAuditoriaDTO`):

### Propiedades de cada Avería:
```typescript
interface SolicitudDetalleDTO {
  id: number;
  solicitud_id: number;
  nombre: string;        // "Freno largo" -> Nombre directo garantizado
  falla_nombre: string;  // "Freno largo" -> Mismo valor (alias seguro)
  resuelto: boolean;
  falta_repuesto: boolean;
  comentario_repuesto?: string;
  mecanico_resolvio_nombre?: string;
  fecha_creacion: string;
  fecha_resolucion?: string;
}
```

### En tus componentes React / TypeScript:
- Para renderizar el nombre de la falla en tarjetas, listas o badges, usa simplemente:
  ```tsx
  <span className="font-bold text-slate-800">
    {det.nombre || det.falla_nombre}
  </span>
  ```
- **Nunca más aparecerá `null`, `undefined` ni `"Desconocido"`**: Si no tiene catálogo, el backend proyecta el texto ingresado directamente.

---

## 4. Agregar Falla desde Supervisión / Taller (`POST /api/v1/supervision/solicitudes/{id}/fallas`)

### Payload Actualizado:
```json
{
  "nombre": "Amortiguador con fuga",
  "autoasignar": false
}
```
No requiere `categoria_id` ni `falla_id`.

---

## 5. Pestaña KPIs y Dashboard de Supervisión (`KpisTab.tsx`)
- Se remueve la sección/gráfico de *"Fallas por Categoría"*, ya que no refleja la naturaleza libre y específica de las averías operativas.
- Las métricas se centran en: Total de fallas, Resueltas, Pendientes y Bloqueadas por repuesto.
