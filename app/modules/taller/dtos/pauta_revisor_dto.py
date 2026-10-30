from pydantic import BaseModel


class PautaMecanicoDTO(BaseModel):
    id: int
    nombre: str


def completar_revisores(data):
    """Normaliza respuestas SQL/ORM y conserva lectura de registros antiguos."""
    if not isinstance(data, dict):
        return data
    result = dict(data)
    mecanicos = result.get("mecanicos") or []
    if not mecanicos and result.get("mecanico_id") is not None:
        mecanicos = [{"id": result["mecanico_id"], "nombre": result.get("mecanico_nombre") or ""}]
    result["mecanicos"] = mecanicos
    result["mecanicos_ids"] = [m["id"] if isinstance(m, dict) else m.id for m in mecanicos]
    return result
