"""Actualiza teléfonos desde un JSON sin crear usuarios nuevos."""
import argparse
import asyncio
import json
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


def normalize_phone(value: str) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("569") and len(digits) == 11:
        return f"+{digits}"
    if digits.startswith("56") and len(digits) == 11 and digits[2] == "9":
        return f"+{digits}"
    if len(digits) == 9 and digits.startswith("9"):
        return f"+56{digits}"
    return None


async def main(json_path: Path) -> None:
    records = json.loads(json_path.read_text(encoding="utf-8-sig"))
    updates = {}
    for record in records:
        rut = (record.get("rut") or "").strip()
        telefono = normalize_phone((record.get("telefono") or "").strip())
        if rut and telefono:
            updates[rut] = telefono

    engine = create_async_engine(settings.async_database_url)
    updated = 0
    async with engine.begin() as conn:
        for rut, telefono in updates.items():
            result = await conn.execute(
                text("UPDATE usuarios SET telefono = :telefono "
                     "WHERE username = :rut AND rol_id = 3"),
                {"rut": rut, "telefono": telefono},
            )
            updated += result.rowcount or 0
        cleaned = await conn.execute(
            text("UPDATE usuarios SET telefono = NULL "
                 "WHERE rol_id = 3 AND telefono IS NOT NULL "
                 "AND telefono !~ '^\\+569[0-9]{8}$'")
        )
    await engine.dispose()
    print(f"registros_json={len(records)} con_telefono={len(updates)} "
          f"actualizados={updated} invalidos_eliminados={cleaned.rowcount or 0}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", type=Path)
    args = parser.parse_args()
    asyncio.run(main(args.json_path))
