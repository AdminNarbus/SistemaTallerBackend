# Backend Taller Narbus 🚀

Proyecto backend para la gestión de taller desarrollado con **FastAPI**, **Python**, **PostgreSQL** y **SQLAlchemy 2.0** (Async & Sync support).

---

## 🛠️ Tecnologías y Características

- **FastAPI**: Framework web asíncrono y de alto rendimiento.
- **SQLAlchemy 2.0**: ORM moderno con soporte de sesión asíncrona (`asyncpg`) y síncrona (`psycopg2`).
- **PostgreSQL**: Base de datos relacional.
- **Pydantic v2**: Validación de esquemas y configuraciones tipadas mediante `pydantic-settings`.
- **Alembic**: Sistema de migraciones de base de datos.
- **Uvicorn**: Servidor ASGI en tiempo real.

---

## 📁 Estructura del Proyecto

```text
BackendTallerNarbus/
├── alembic/                  # Migraciones de base de datos
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── app/                      # Aplicación principal FastAPI
│   ├── api/                  # Endpoints y rutas de la API
│   │   ├── deps.py           # Inyección de dependencias (DB session)
│   │   └── v1/
│   │       ├── endpoints/    # Sub-recursos (health, items, etc.)
│   │       └── router.py     # Enrutador API V1
│   ├── core/                 # Configuración de entorno y conexión a DB
│   │   ├── config.py
│   │   └── database.py
│   ├── crud/                 # Lógica de acceso y manipulación de datos (CRUD)
│   ├── models/               # Modelos SQLAlchemy ORM
│   ├── schemas/              # Esquemas Pydantic para Request/Response
│   └── main.py               # Entrada principal de la aplicación FastAPI
├── .env                      # Variables de entorno locales
├── .env.example              # Plantilla de variables de entorno
├── .gitignore
├── alembic.ini               # Configuración de Alembic
├── README.md
└── requirements.txt          # Dependencias del proyecto
```

---

## 🚀 Guía de Inicio Rápido

### 1. Crear e Iniciar el Entorno Virtual (Python)

```bash
# En Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# En Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 2. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar la Base de Datos PostgreSQL

Asegúrate de tener un servidor PostgreSQL ejecutándose y crea la base de datos:
```sql
CREATE DATABASE taller_narbus;
```

Edita las credenciales en el archivo `.env` según tu entorno:
```env
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=tu_contraseña
POSTGRES_DB=taller_narbus
```

### 4. Ejecución por Perfiles / Entornos

El proyecto cuenta con 3 perfiles preconfigurados de ejecución:

| Perfil | Flag / Comando | Host | Auto-reload | Acceso CORS | Documentación `/docs` |
|---|---|---|---|---|---|
| **Dev Full Local** | `python run.py --local` | `127.0.0.1` | ✅ Activado | Estricto (localhost/127.0.0.1) | ✅ Habilitada |
| **Dev Red Local (LAN)** | `python run.py --lan` | `0.0.0.0` | ✅ Activado | Abierto (Red Local / Capacitor) | ✅ Habilitada |
| **Producción** | `python run.py --prod` | `0.0.0.0` | ❌ Desactivado | Dominios explícitos `BACKEND_CORS_ORIGINS` | ❌ Deshabilitada (Seguridad) |

#### Ejemplos de comando:

```bash
# 1. Desarrollo Full Local (exclusivo para este equipo)
python run.py --local

# 2. Desarrollo Red Local (para conectar celulares / otros PC de la red)
python run.py --lan

# 3. Producción
python run.py --prod

# También puedes especificar la variable ENVIRONMENT en tu archivo .env:
# ENVIRONMENT=dev_local
# ENVIRONMENT=dev_lan
# ENVIRONMENT=production
```

---



## 📚 Documentación Interactiva

FastAPI genera automáticamente documentación interactiva disponible en:

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 🗄️ Migraciones con Alembic

Para generar una nueva migración automáticamente tras actualizar los modelos:

```bash
alembic revision --autogenerate -m "Descripción del cambio"
```

Para aplicar las migraciones pendientes a la base de datos:

```bash
alembic upgrade head
```
