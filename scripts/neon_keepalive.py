#!/usr/bin/env python
"""
Script standalone para mantener despierta la base de datos serverless de Neon (keep-alive).
Emite un pulso 'SELECT 1' cada 3 minutos (180 segundos) para evitar que el cómputo
serverless de Neon se suspenda por inactividad (timeout de 5 min).

Uso:
    python scripts/neon_keepalive.py
"""
import asyncio
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

# Cargar variables de entorno desde .env en la raíz del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("[ERROR] DATABASE_URL no encontrada en el archivo .env")
    sys.exit(1)

# Asegurar driver asyncpg para SQLAlchemy asíncrono
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

INTERVAL_SECONDS = 180  # 3 minutos


async def run_keepalive():
    print("=" * 70)
    print("  NARBUS TALLER - KEEPALIVE STANDALONE PARA NEON POSTGRESQL")
    print(f"  Intervalo de pulso: {INTERVAL_SECONDS} segundos (3 minutos)")
    print(f"  Objetivo: Prevenir cold-start de 3s por suspensión de cómputo")
    print("  Presiona CTRL+C para detener el servicio.")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada")

    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=False,
        pool_recycle=300,
    )

    try:
        # Pulso inicial inmediato
        t0 = time.perf_counter()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        rtt_ms = (time.perf_counter() - t0) * 1000
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now_str}] [INICIO] Conexión establecida | RTT inicial={rtt_ms:.1f} ms")

        # Bucle periódico
        while True:
            await asyncio.sleep(INTERVAL_SECONDS)
            t0 = time.perf_counter()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            rtt_ms = (time.perf_counter() - t0) * 1000
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{now_str}] [PULSO] Neon activo (24/7 caliente) | RTT={rtt_ms:.1f} ms")

    except asyncio.CancelledError:
        print("\n[INFO] Deteniendo bucle de keepalive...")
    except KeyboardInterrupt:
        print("\n[INFO] Detenido por el usuario.")
    except Exception as exc:
        print(f"\n[ERROR] Fallo en conexión a Neon: {exc}")
    finally:
        await engine.dispose()
        print("[INFO] Motor desconectado.")


if __name__ == "__main__":
    try:
        asyncio.run(run_keepalive())
    except KeyboardInterrupt:
        pass
