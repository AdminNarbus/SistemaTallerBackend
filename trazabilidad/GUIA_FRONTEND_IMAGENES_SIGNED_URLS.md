# Guía para el Frontend: Almacenamiento Seguro con Bucket Privado y Signed URLs

Esta guía técnica explica la arquitectura de visualización y subida de imágenes en **Narbus Taller**, implementando el estándar de la industria: **Bucket 100% Privado en Google Cloud Storage + URLs Firmadas Temporales (Signed URLs)**.

---

## 1. Concepto Clave: ¿Qué es una Signed URL?

Las imágenes de las averías, buses e inspecciones **no son públicas**. Nadie en internet puede verlas sin autorización.

1. El bucket de Google Cloud Storage tiene bloqueado todo acceso anónimo.
2. Cuando el usuario autenticado (chofer, mecánico, supervisor) consulta una solicitud al Backend, el Backend genera una **Signed URL (URL firmada criptográficamente)** con un tiempo de validez de **60 minutos**.
3. El frontend recibe una URL como esta:
   ```text
   https://storage.googleapis.com/narbus-taller-media/solicitudes/d1897339-44ce-4c7a-b7f5-d9da4c95ee09.jpg?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=...&X-Goog-Date=...&X-Goog-Expires=3600&X-Goog-SignedHeaders=host&X-Goog-Signature=...
   ```
4. El navegador descarga la imagen directamente desde los servidores de Google (alta velocidad, caché optimizada y sin recargar el contenedor de Cloud Run).
5. **Seguridad:** Si alguien copia el enlace y pasan más de 60 minutos, la URL expira automáticamente y Google devuelve `403 Forbidden`.

---

## 2. Cómo se Consumen las Imágenes en el Frontend

¡Buenas noticias para el Frontend! **No necesitas instalar ninguna librería de Google Cloud ni configurar SDKs en React/Vite.**

### Uso Directo en Componentes React
Puedes usar la URL directamente en la etiqueta estándar `<img>`:

```tsx
interface SolicitudProps {
  solicitud: {
    id: number;
    n_bus: string;
    descripcion_general: string;
    foto_url?: string | null;
    evidencias?: Array<{ url: string; original_filename?: string }>;
  };
}

export const TarjetaSolicitud = ({ solicitud }: SolicitudProps) => {
  return (
    <div className="tarjeta-solicitud">
      <h3>Bus: {solicitud.n_bus}</h3>
      <p>{solicitud.descripcion_general}</p>

      {/* Renderizado directo de la foto principal */}
      {solicitud.foto_url ? (
        <img 
          src={solicitud.foto_url} 
          alt={`Evidencia Bus ${solicitud.n_bus}`} 
          className="w-full h-48 object-cover rounded-lg"
          loading="lazy"
        />
      ) : (
        <div className="placeholder-foto">Sin foto adjunta</div>
      )}

      {/* Galería de múltiples evidencias si existen */}
      {solicitud.evidencias && solicitud.evidencias.length > 0 && (
        <div className="galeria-fotos flex gap-2 mt-2">
          {solicitud.evidencias.map((evidencia, idx) => (
            <img
              key={idx}
              src={evidencia.url}
              alt={`Evidencia ${idx + 1}`}
              className="w-16 h-16 object-cover rounded"
            />
          ))}
        </div>
      )}
    </div>
  );
};
```

---

## 3. Utilidad Recomendada: `src/utils/imageUrl.ts`

Para garantizar que el frontend funcione de manera transparente tanto en **desarrollo local** (`http://localhost:8000/uploads/...`) como en **producción en la nube** (Signed URLs de GCS), se recomienda tener esta función utilitaria:

```typescript
// src/utils/imageUrl.ts

const BACKEND_API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

/**
 * Normaliza cualquier URL de imagen recibida del Backend:
 * - Si es una Signed URL completa (https://storage.googleapis.com/...), la retorna intacta.
 * - Si es una ruta relativa local (/uploads/...), le añade la URL base del backend si es necesario.
 * - Si viene vacía o null, retorna una imagen placeholder por defecto.
 */
export function getCleanImageUrl(
  url?: string | null,
  placeholder = "/assets/placeholder-bus.png"
): string {
  if (!url || typeof url !== "string" || url.trim() === "") {
    return placeholder;
  }

  const cleanUrl = url.trim();

  // 1. Signed URLs de Google Cloud Storage (Producción)
  if (cleanUrl.startsWith("https://storage.googleapis.com") || cleanUrl.startsWith("http://") || cleanUrl.startsWith("https://")) {
    return cleanUrl;
  }

  // 2. Rutas relativas locales (Desarrollo local /uploads/...)
  if (cleanUrl.startsWith("/")) {
    // Si la URL del backend no termina en slash y la ruta empieza con slash
    const base = BACKEND_API_BASE_URL.replace(/\/+$/, "");
    return `${base}${cleanUrl}`;
  }

  return `${BACKEND_API_BASE_URL}/${cleanUrl}`;
}
```

---

## 4. Subida de Imágenes (Formulario Multipart en 1 Solo Request)

El proceso de subida **no cambia**: se sigue enviando el archivo en un único request `multipart/form-data`:

```typescript
// Ejemplo de envío de solicitud con foto adjunta
export async function crearSolicitudConFoto(formDataOriginal: {
  n_bus: string;
  descripcion_general: string;
  archivoFoto?: File | null;
}) {
  const formData = new FormData();
  formData.append("n_bus", formDataOriginal.n_bus);
  formData.append("descripcion_general", formDataOriginal.descripcion_general);

  // Adjuntar el archivo binario capturado con la cámara o galería
  if (formDataOriginal.archivoFoto) {
    formData.append("foto", formDataOriginal.archivoFoto);
  }

  const token = localStorage.getItem("token"); // o desde tu store de Auth

  const response = await fetch(`${BACKEND_API_BASE_URL}/api/v1/mantencion/solicitudes`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      // NOTA: NO colocar 'Content-Type': 'multipart/form-data', el navegador lo coloca automáticamente con el boundary
    },
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData?.error?.message || "Error al crear solicitud");
  }

  const data = await response.json();
  // data.foto_url ya vendrá con la Signed URL lista
  return data;
}
```

---

## 5. Preguntas Frecuentes (FAQ)

### ¿Qué pasa si una pestaña queda abierta más de 60 minutos y la Signed URL expira?
Si el usuario deja la pantalla abierta más de 60 minutos, la URL expira. Al recargar la lista o volver a consultar el detalle de la solicitud (`GET /api/v1/mantencion/solicitudes/{id}`), el backend generará automáticamente una nueva Signed URL fresca con otros 60 minutos de vigencia.

### ¿Se necesita enviar el token JWT al cargar la imagen?
**No.** La etiqueta `<img src="..." />` hace una petición GET directa a los servidores de Google Cloud Storage. La autenticación la realiza Google validando la firma criptográfica incluida en los parámetros de la URL (`?X-Goog-Signature=...`).

### ¿Las fotos son privadas?
**Sí, 100% privadas.** Nadie sin una sesión activa en el sistema puede solicitarle al backend que le firme una URL, y las firmas caducan automáticamente tras su tiempo de expiración.
