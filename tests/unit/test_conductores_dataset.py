import pytest
from app.core.seeds.conductores_dataset import CONDUCTORES_DATASET
from app.core.security import verify_password


def test_conductores_dataset_total_count():
    """Verifica que el dataset contenga exactamente los 124 conductores de la flota."""
    assert len(CONDUCTORES_DATASET) == 124, f"Se esperaban 124 conductores, pero hay {len(CONDUCTORES_DATASET)}"


def test_conductores_dataset_unicidad_y_formato_rut():
    """Verifica la unicidad absoluta de RUTs y formato chileno estándar (sin puntos, con guión)."""
    ruts = set()
    for c in CONDUCTORES_DATASET:
        rut = c["rut"]
        assert rut, "El RUT no puede ser nulo ni vacío"
        assert "." not in rut, f"El RUT '{rut}' contiene puntos indebidos"
        assert "-" in rut, f"El RUT '{rut}' debe contener guión separador de dígito verificador"
        assert rut not in ruts, f"RUT duplicado en dataset: {rut}"
        ruts.add(rut)


def test_conductores_dataset_campos_obligatorios_y_hashes():
    """Verifica que todos los campos requeridos existan y los hashes bcrypt coincidan con la clave."""
    for c in CONDUCTORES_DATASET:
        assert c["nombre"], f"Nombre faltante para RUT {c['rut']}"
        assert c["apellido"], f"Apellido faltante para RUT {c['rut']}"
        assert c["is_active"] is True, f"El estado debe ser True para {c['rut']}"
        assert c["clave"], f"Clave faltante para RUT {c['rut']}"
        assert c["password_hash"].startswith("$2b$") or c["password_hash"].startswith("$2a$"), f"Hash bcrypt inválido para {c['rut']}"
        
        # Verificar coincidencia de clave con hash
        assert verify_password(c["clave"], c["password_hash"]), f"La clave '{c['clave']}' no coincide con el hash para RUT {c['rut']}"
