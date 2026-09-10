# Guía Técnica de Integración para el Frontend: Almacenamiento Cloud de Imágenes en 1 Solo Request HTTP

## 1. Resumen Ejecutivo y Arquitectura (Zero Bottlenecks)

El Backend de Taller Narbus cuenta con almacenamiento de fotografías en **Google Cloud Storage (GCS)** y Disco Local con persistencia relacional en PostgreSQL (Tercera Forma Normal - 3NF) mediante un **servicio interno desacoplado (`StorageService`)**.

### Decisión de Diseño: 1 Solo Request HTTP y Soporte de Múltiples Fotos
Para evitar **cuellos de botella**, peticiones de red compuestas y esperas innecesarias en el Frontend:
1. **NO se requiere un endpoint previo de subida:** El Frontend **NO** tiene que hacer dos o más peticiones secuenciales (`/upload` y luego `/formulario`).
2. **Envío Atómico en 1 Solo Viaje:** El Frontend envía el formulario y todos los archivos fotográficos en **una única petición HTTP (`multipart/form-data`)**.
3. **Soporte de Múltiples Imágenes de Evidencia:** El conductor o mecánico puede adjuntar **varias fotografías** de la avería (ej. rueda, tablero, freno). El backend las procesa todas concurrentemente en el mismo request.
4. **El Backend se encarga de todo:**
   * Recibe el formulario y los archivos binarios (`fotos` o `foto`).
   * Sube cada imagen directamente a Google Cloud Storage de forma asíncrona no bloqueante.
   * Persiste la orden en PostgreSQL y crea los registros en la tabla relacional `taller_solicitud_evidencias`.
   * Asigna automáticamente la primera foto como `foto_url` principal para total retrocompatibilidad.
   * Retorna la entidad con la lista de `evidencias: [...]`.
5. **Cero "Imágenes Huérfanas":** Si la validación de la orden falla (ej. patente inválida o bus inexistente), no quedan imágenes abandonadas en la nube.
6. **Máxima Velocidad en Conexiones Móviles:** El chofer en ruta solo realiza **un único envío**, protegiendo la transacción frente a microcortes de red.

---

## 2. Integración en los Formularios

### A. Formulario de Mantención / Averías (`POST /api/v1/mantencion/solicitudes`)

El endpoint soporta **tres modalidades** con total retrocompatibilidad:

#### Modalidad 1: Envío de Múltiples Fotos en `FormData` (RECOMENDADA)
* **Método:** `POST`
* **URL:** `/api/v1/mantencion/solicitudes`
* **Content-Type:** `multipart/form-data`
* **Headers:** `Authorization: Bearer <token>`

**Campos del Formulario (`FormData`):**
| Campo | Tipo | Requerido | Descripción / Ejemplo |
| :--- | :--- | :--- | :--- |
| `n_bus` | `string` | **Sí** (o `bus_id`) | `"339"` |
| `bus_id` | `number` / `string` | Opcional | `12` |
| `descripcion_general` | `string` | Opcional | `"Múltiples fallas detectadas en ruta"` |
| `fotos` | `File` (Repetido) | Opcional | **Adjuntar múltiples veces:** `formData.append('fotos', file)`. También se admite `fotos[]` o `evidencias`. |
| `foto` | `File` | Opcional | (Retrocompatibilidad) Si solo se envía 1 sola foto con la clave `foto`. |
| `detalles` | `string` (JSON) | Opcional | Arreglo JSON de fallas: `[{"categoria_id": 1, "descripcion_personalizada": "Pastillas gastadas"}]` |

> [!TIP]
> **¿Cómo adjuntar múltiples archivos en JavaScript/TypeScript?**
> Con un `<input type="file" multiple />`, simplemente itera los archivos y llama a `formData.append('fotos', file)` para cada uno:
> ```typescript
> Array.from(selectedFiles).forEach((file) => {
>   formData.append('fotos', file);
> });
> ```

#### Modalidad 2: Envío Tradicional JSON (`application/json`)
Si las fotos ya se encuentran almacenadas o provienen de URLs externas:
```json
POST /api/v1/mantencion/solicitudes
Content-Type: application/json

{
  "n_bus": "339",
  "bus_id": 12,
  "descripcion_general": "Fallas reportadas",
  "foto_url": "https://storage.googleapis.com/.../principal.jpg",
  "fotos_urls": [
    "https://storage.googleapis.com/.../foto1.jpg",
    "https://storage.googleapis.com/.../foto2.jpg"
  ],
  "detalles": [ ... ]
}
```

---

### B. Formulario de Neumáticos (`POST /api/v1/neumaticos/formularioNeumatico`)

Mantiene exactamente la misma estructura que ya utiliza el Frontend:
* **Método:** `POST`
* **URL:** `/api/v1/neumaticos/formularioNeumatico`
* **Content-Type:** `multipart/form-data`
* **Campo de Archivo:** `evidencia: (File)`
* **Resultado:** El Backend sube el archivo a Google Cloud Storage y guarda la URL pública en `evidencia_url`.

---

## 3. Estructura de Respuesta del Backend (`SolicitudDTO`)

Cuando se crea o consulta una solicitud, el Backend entrega:

```json
{
  "id": 42,
  "n_bus": "339",
  "bus_id": 12,
  "bus_patente": "CC3399",
  "estado": "REPORTADO",
  "descripcion_general": "Múltiples averías detectadas en ruta",
  "foto_url": "https://storage.googleapis.com/narbus-taller-media/solicitudes/uuid-1.jpg",
  "fecha_creacion": "2026-09-10T10:15:00Z",
  "evidencias": [
    {
      "id": 101,
      "solicitud_id": 42,
      "detalle_id": null,
      "usuario_id": 7,
      "url": "https://storage.googleapis.com/narbus-taller-media/solicitudes/uuid-1.jpg",
      "original_filename": "rueda_delantera.jpg",
      "size_bytes": 1048576,
      "content_type": "image/jpeg",
      "fecha_creacion": "2026-09-10T10:15:00Z"
    },
    {
      "id": 102,
      "solicitud_id": 42,
      "detalle_id": null,
      "usuario_id": 7,
      "url": "https://storage.googleapis.com/narbus-taller-media/solicitudes/uuid-2.jpg",
      "original_filename": "fuga_aceite.jpg",
      "size_bytes": 2097152,
      "content_type": "image/jpeg",
      "fecha_creacion": "2026-09-10T10:15:00Z"
    }
  ],
  "detalles": [ ... ]
}
```

* **`foto_url`:** Es la primera imagen subida. Si el frontend existente solo lee `foto_url`, seguirá mostrando la foto principal sin necesidad de cambios inmediatos.
* **`evidencias`:** Es el arreglo completo con todas las fotos adjuntas y sus metadatos (tamaño, nombre original, fecha).

---

## 4. Visualización de Fotografías en Pantalla (`<img>`)

Tanto en Google Cloud Storage como en local, se recomienda la siguiente función utilitaria:

```typescript
// utils/imageUrl.ts
const BACKEND_URL = import.meta.env.VITE_API_URL?.replace('/api/v1', '') || 'http://localhost:8000';

export function getFullImageUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  
  // Si ya es una URL completa de Google Cloud Storage
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }
  
  // Si es una ruta relativa local (/uploads/...)
  return `${BACKEND_URL}${url.startsWith('/') ? '' : '/'}${url}`;
}
```

---

## 5. Ejemplo de Código en React / TypeScript

### A. Servicio API para Enviar Múltiples Fotos

```typescript
// services/mantencionService.ts
import axios from 'axios';

export interface CrearSolicitudConEvidenciasPayload {
  n_bus: string;
  bus_id?: number;
  descripcion_general?: string;
  fotos?: File[];
  detalles?: Array<{ categoria_id: number; descripcion_personalizada?: string }>;
}

export async function crearSolicitudConEvidencias(payload: CrearSolicitudConEvidenciasPayload) {
  const token = localStorage.getItem('token');
  const formData = new FormData();

  formData.append('n_bus', payload.n_bus);
  if (payload.bus_id) formData.append('bus_id', payload.bus_id.toString());
  if (payload.descripcion_general) formData.append('descripcion_general', payload.descripcion_general);

  // Adjuntar cada archivo bajo la misma clave 'fotos'
  if (payload.fotos && payload.fotos.length > 0) {
    payload.fotos.forEach((file) => {
      formData.append('fotos', file);
    });
  }

  // Serializar el arreglo de averías
  if (payload.detalles && payload.detalles.length > 0) {
    formData.append('detalles', JSON.stringify(payload.detalles));
  }

  const response = await axios.post(
    `${import.meta.env.VITE_API_URL}/mantencion/solicitudes`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
        Authorization: `Bearer ${token}`,
      },
    }
  );

  return response.data; // SolicitudDTO con foto_url y evidencias[]
}
```

### B. Componente de Formulario con Selector Múltiple y Galería

```tsx
// components/FormularioSolicitudChofer.tsx
import React, { useState } from 'react';
import { crearSolicitudConEvidencias } from '../services/mantencionService';
import { getFullImageUrl } from '../utils/imageUrl';

export const FormularioSolicitudChofer: React.FC = () => {
  const [nBus, setNBus] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [fotos, setFotos] = useState<File[]>([]);
  const [enviando, setEnviando] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      // Agregar nuevos archivos a la lista
      setFotos((prev) => [...prev, ...Array.from(e.target.files!)]);
    }
  };

  const handleEliminarFoto = (index: number) => {
    setFotos((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    try {
      const solicitud = await crearSolicitudConEvidencias({
        n_bus: nBus,
        descripcion_general: descripcion,
        fotos: fotos,
      });
      alert(`¡Solicitud #${solicitud.id} creada con ${solicitud.evidencias?.length || 0} fotos!`);
      setFotos([]);
    } catch (err: any) {
      alert(`Error al enviar solicitud: ${err?.response?.data?.error?.message || err.message}`);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="p-4 space-y-4 max-w-md mx-auto">
      <div>
        <label className="block font-semibold">N° de Bus:</label>
        <input
          type="text"
          value={nBus}
          onChange={(e) => setNBus(e.target.value)}
          required
          className="w-full border p-2 rounded"
          placeholder="Ej: 339"
        />
      </div>

      <div>
        <label className="block font-semibold">Descripción de la Falla:</label>
        <textarea
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
          className="w-full border p-2 rounded"
          placeholder="Describa el problema observado..."
        />
      </div>

      <div>
        <label className="block font-semibold">Fotos de Evidencia (puedes seleccionar varias):</label>
        <input
          type="file"
          multiple
          accept="image/jpeg,image/png,image/webp"
          onChange={handleFileChange}
          className="w-full border p-2 rounded"
        />
      </div>

      {/* Vista previa de fotos a subir */}
      {fotos.length > 0 && (
        <div className="grid grid-cols-3 gap-2 mt-2">
          {fotos.map((file, i) => (
            <div key={i} className="relative border rounded p-1">
              <img
                src={URL.createObjectURL(file)}
                alt={`preview-${i}`}
                className="w-full h-20 object-cover rounded"
              />
              <button
                type="button"
                onClick={() => handleEliminarFoto(i)}
                className="absolute top-0 right-0 bg-red-600 text-white rounded-full w-5 h-5 text-xs flex items-center justify-center"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <button
        type="submit"
        disabled={enviando}
        className="w-full bg-blue-600 text-white py-2 px-4 rounded font-bold hover:bg-blue-700 disabled:opacity-50"
      >
        {enviando ? 'Subiendo orden y fotos...' : `Enviar Solicitud (${fotos.length} fotos)`}
      </button>
    </form>
  );
};
```

---

## 6. Resumen de Beneficios para el Frontend

| Aspecto | Antes (1 Sola Foto) | Ahora (Múltiples Evidencias 3NF) |
| :--- | :--- | :--- |
| **Cantidad de Fotos** | Máximo 1 sola foto | **Ilimitadas fotos de evidencia** por solicitud |
| **Peticiones HTTP** | 1 petición `multipart/form-data` | **1 sola petición HTTP atómica** (sin endpoints previos de subida) |
| **Formato de Envío** | `formData.append('foto', file)` | `formData.append('fotos', file)` múltiples veces |
| **Respuesta del Servidor** | `foto_url: string` | `foto_url: string` (principal) + `evidencias: SolicitudEvidenciaDTO[]` |
| **Retrocompatibilidad** | N/A | **100% retrocompatible:** Componentes viejos leen `foto_url`, componentes nuevos leen `evidencias` |
