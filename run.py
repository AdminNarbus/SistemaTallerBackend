import argparse
import os
import sys
import uvicorn

# Argumentos CLI
parser = argparse.ArgumentParser(description="Backend Taller Narbus - Launcher de Servidor")
parser.add_argument(
    "--env",
    type=str,
    choices=["dev_local", "dev_lan", "production"],
    help="Perfil de entorno a ejecutar (dev_local | dev_lan | production)",
)
parser.add_argument("--local", action="store_true", help="Acceso directo a perfil dev_local")
parser.add_argument("--lan", action="store_true", help="Acceso directo a perfil dev_lan")
parser.add_argument("--prod", action="store_true", help="Acceso directo a perfil production")
parser.add_argument("--host", type=str, help="Host IP personalizado para uvicorn")
parser.add_argument("--port", type=int, help="Puerto personalizado para uvicorn")

args = parser.parse_args()

# Determinar perfil elegido
target_env = None
if args.local:
    target_env = "dev_local"
elif args.lan:
    target_env = "dev_lan"
elif args.prod:
    target_env = "production"
elif args.env:
    target_env = args.env

if target_env:
    os.environ["ENVIRONMENT"] = target_env

if args.host:
    os.environ["HOST"] = args.host

if args.port:
    os.environ["PORT"] = str(args.port)

# Importar settings con las variables de entorno aplicadas
from app.core.config import settings, AppEnvironment

def main():
    host = settings.server_host
    port = settings.PORT
    reload_enabled = settings.is_reload_enabled

    print("=" * 65)
    print(f"INICIANDO {settings.PROJECT_NAME.upper()} (v{settings.VERSION})")
    print("=" * 65)
    print(f"[*] PERFIL ACTIVO      : {settings.ENVIRONMENT.value.upper()}")
    print(f"[*] ESCUCHANDO EN       : http://{host}:{port}")
    print(f"[*] AUTO-RELOAD        : {'ACTIVADO' if reload_enabled else 'DESACTIVADO'}")
    
    if settings.ENVIRONMENT == AppEnvironment.DEV_LOCAL:
        print("[*] MODO DE SEGURIDAD  : Exclusivo para la maquina local (127.0.0.1)")
    elif settings.ENVIRONMENT == AppEnvironment.DEV_LAN:
        print("[*] MODO DE SEGURIDAD  : Abierto a dispositivos de la red local (0.0.0.0)")
    else:
        print("[*] MODO DE SEGURIDAD  : Produccion estricto")

    if settings.docs_url:
        docs_host = "localhost" if host == "0.0.0.0" else host
        print(f"[*] SWAGGER DOCS        : http://{docs_host}:{port}{settings.docs_url}")
    else:
        print("[*] SWAGGER DOCS        : Deshabilitados (Produccion)")

    print("=" * 65)

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
    )

if __name__ == "__main__":
    main()
