# Guía Operativa de Despliegue Continuo (CI/CD) en Google Cloud
## Backend Taller Narbus (Cloud Build + Cloud Run + Artifact Registry + Secret Manager)

Esta guía documenta la puesta en marcha del pipeline de despliegue continuo en la nube de Google Cloud sincronizado nativamente con el repositorio de Git, sin requerir GitHub Actions ni herramientas intermedias.

---

## 1. Arquitectura del Pipeline

```mermaid
flowchart TD
    A[Push en Git<br>rama develop / main] -->|Webhook Nativo| B[Google Cloud Build Trigger]
    B -->|Paso 1: Cache Pull| C[Descargar última imagen de Artifact Registry]
    B -->|Paso 2: Docker Build| D[Compilar imagen con SHA y latest]
    B -->|Paso 3: Push Registry| E[Publicar en Artifact Registry]
    B -->|Paso 4: gcloud run deploy| F[Google Cloud Run]
    F -->|Inyección de Secretos| G[Secret Manager: DATABASE_URL, SECRET_KEY]
    F -->|Entrypoint Automático| H[alembic upgrade head en Neon]
    F -->|Arranque del Servidor| I[Uvicorn en puerto 8000]
    F -->|Evidencias Fotográficas| J[Google Cloud Storage Bucket]
```

### Componentes de Google Cloud
1. **Cloud Build (`cloudbuild.yaml`):** Motor de integración y despliegue continuo conectado a Git.
2. **Artifact Registry:** Repositorio privado de contenedores Docker (`us-central1-docker.pkg.dev/$PROJECT_ID/narbus-backend/narbus-backend-api`).
3. **Cloud Run:** Plataforma Serverless que ejecuta el contenedor con auto-escalado (0 a 10 instancias), TLS/HTTPS automático y balanceo de carga.
4. **Secret Manager:** Custodia segura de credenciales sensibles (`DATABASE_URL`, `SECRET_KEY`), inyectadas en tiempo de ejecución.
5. **Google Cloud Storage (GCS):** Bucket para evidencias de mantención y neumáticos subidas directamente por los servicios.

---

## 2. Paso a Paso para Configuración Inicial en Google Cloud Console

### Paso 1: Habilitar las APIs de Google Cloud
En la consola web de Google Cloud ([console.cloud.google.com](https://console.cloud.google.com/)) o vía terminal de Cloud Shell, asegurarse de tener habilitadas las APIs:
- **Cloud Build API** (`cloudbuild.googleapis.com`)
- **Cloud Run Admin API** (`run.googleapis.com`)
- **Artifact Registry API** (`artifactregistry.googleapis.com`)
- **Secret Manager API** (`secretmanager.googleapis.com`)
- **Cloud Logging API** (`logging.googleapis.com`)

### Paso 2: Crear el Repositorio en Artifact Registry
1. Ir a **Artifact Registry** > **Repositorios** > **Crear Repositorio**.
2. Configurar:
   - **Nombre:** `narbus-backend`
   - **Formato:** `Docker`
   - **Modo:** Estándar
   - **Región:** `us-central1` (o la región elegida, ej. `southamerica-west1`).
3. Clic en **Crear**.

### Paso 3: Crear los Secretos en Secret Manager
1. Ir a **Security** > **Secret Manager** > **Crear Secreto**.
2. Crear el secreto **`DATABASE_URL`**:
   - **Nombre:** `DATABASE_URL`
   - **Valor:** Cadena de conexión asyncpg hacia la base de datos de Neon (ej: `postgresql+asyncpg://usuario:password@ep-xyz.us-east-2.aws.neon.tech/neondb?ssl=require`).
3. Crear el secreto **`SECRET_KEY`**:
   - **Nombre:** `SECRET_KEY`
   - **Valor:** Cadena aleatoria de alta entropía para firma de tokens JWT (ej. hash seguro de 64 caracteres).

### Paso 4: Otorgar Permisos IAM a la Cuenta de Cloud Build
Para que Cloud Build pueda desplegar en Cloud Run e inyectar secretos, la Service Account de Cloud Build requiere los roles adecuados:
1. Ir a **IAM y Administración** > **IAM**.
2. Buscar la cuenta de servicio de Cloud Build (típicamente `[NUMERO_PROYECTO]@cloudbuild.gserviceaccount.com` o la cuenta de servicio de cómputo predeterminada `[NUMERO_PROYECTO]-compute@developer.gserviceaccount.com`).
3. Asignar los siguientes roles:
   - **Administrador de Cloud Run** (`roles/run.admin`)
   - **Usuario de cuenta de servicio** (`roles/iam.serviceAccountUser`)
   - **Descriptor de acceso a secretos de Secret Manager** (`roles/secretmanager.secretAccessor`)

---

## 3. Conectar el Repositorio Git y Crear el Disparador (Trigger)

### Paso 5: Conectar el Repositorio en Cloud Build
1. Ir a **Cloud Build** > **Repositorios** (2da generación) o **Triggers**.
2. Seleccionar **Conectar Repositorio** y elegir **GitHub** (vía GitHub App de Google Cloud Build).
3. Autorizar la cuenta de GitHub y seleccionar el repositorio `BackendTallerNarbus`.

### Paso 6: Crear el Disparador (Trigger)
1. Ir a **Cloud Build** > **Disparadores (Triggers)** > **Crear Disparador**.
2. Configurar los campos:
   - **Nombre:** `deploy-backend-taller-develop`
   - **Evento:** **Enviar a una rama** (`Push to a branch`).
   - **Repositorio:** Seleccionar el repositorio conectado.
   - **Rama:** `^develop$` (o `^main$` para producción).
   - **Configuración de compilación:** **Archivo de configuración de Cloud Build (yaml o json)**.
   - **Ubicación del archivo:** `cloudbuild.yaml` (en la raíz del repositorio).
3. **Variables de sustitución (Opcional si se desea sobreescribir los valores por defecto):**
   - `_REGION`: `us-central1`
   - `_SERVICE_NAME`: `narbus-backend-api`
   - `_REPO_NAME`: `narbus-backend`
   - `_SECRET_DATABASE_URL`: `DATABASE_URL`
   - `_SECRET_KEY`: `SECRET_KEY`
   - `_GCS_BUCKET_NAME`: `narbus-taller-media`
4. Clic en **Crear**.

---

## 4. Ejecución del Despliegue y Ciclo de Vida del Contenedor

### ¿Qué sucede cuando haces `git push origin develop`?
1. **Detección Automática:** Google Cloud Build recibe el evento de push de Git en menos de 2 segundos.
2. **Build Eficiente:** Reutiliza las capas Docker cacheadas de la compilación anterior para compilar la nueva imagen en ~30-60 segundos.
3. **Etiquetado Dual:** Publica la imagen en Artifact Registry con la etiqueta inmutable `$COMMIT_SHA` y la etiqueta flotante `:latest`.
4. **Despliegue a Cloud Run:** Cloud Run lanza una nueva revisión del servicio `narbus-backend-api`.
5. **Auto-Migración (Alembic):** El script `docker-entrypoint.sh` ejecuta `alembic upgrade head` contra Neon antes de que Uvicorn comience a aceptar peticiones HTTP, garantizando integridad de esquema 3NF.
6. **Traffic Migration:** Cloud Run conmuta el 100% del tráfico a la nueva versión sin tiempo de inactividad (Zero Downtime).

---

## 5. Verificación de Salud en Producción

Una vez finalizado el despliegue, Cloud Run proporcionará una URL pública segura (ej: `https://narbus-backend-api-xyz-uc.a.run.app`).

### Comprobaciones Recomendadas:
1. **Liveness Probe (Verificación de Servidor Vivo):**
   ```bash
   curl -i https://[TU_URL_CLOUD_RUN]/api/v1/health/live
   ```
   **Respuesta esperada:** `HTTP/1.1 200 OK`
   ```json
   {"status":"healthy","timestamp":"2026-09-10T..."}
   ```

2. **Readiness Probe (Verificación de Base de Datos y Neon):**
   ```bash
   curl -i https://[TU_URL_CLOUD_RUN]/api/v1/health/db
   ```
   **Respuesta esperada:** `HTTP/1.1 200 OK`
   ```json
   {"database":"connected","environment":"production"}
   ```

3. **Catálogo OpenAPI e Interfaz Swagger:**
   Acceder a `https://[TU_URL_CLOUD_RUN]/docs` para verificar la disponibilidad de los 43 endpoints REST de los módulos de Auth, Buses, Mantención, Neumáticos y Supervisión.

---

## 6. Resolución de Problemas Frecuentes

| Síntoma | Causa Probable | Solución |
| --- | --- | --- |
| `Cloud Build falla en el paso 4 (Permission Denied)` | La Service Account de Cloud Build no tiene rol `Cloud Run Admin` o `Service Account User`. | Asignar roles en IAM según el Paso 4. |
| `Cloud Run falla al iniciar (CrashLoop / Error 503)` | `DATABASE_URL` mal configurada o el secreto no existe en Secret Manager. | Verificar que el secreto `DATABASE_URL` esté creado y que el rol `Secret Manager Secret Accessor` esté otorgado. |
| `Migraciones de Alembic fallan al arrancar` | Bloqueo transaccional en PostgreSQL o credenciales inválidas. | Revisar logs en **Cloud Logging** filtrando por `resource.type="cloud_run_revision"`. |
| `Error de CORS desde el Frontend` | El dominio del frontend no está incluido en `BACKEND_CORS_ORIGINS`. | Añadir el dominio del frontend a la variable de entorno `BACKEND_CORS_ORIGINS` o pasar `CORS_ORIGIN_REGEX` en Cloud Run. |
