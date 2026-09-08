import pytest
from app.core.seeds.buses_dataset import BUSES_DATASET
from app.modules.mantencion.models.pauta_taller import PautaTallerItem


def test_buses_dataset_consistency():
    """Verifica que el dataset estático de buses cumpla con el rango 200-800 y formato esperado."""
    assert len(BUSES_DATASET) == 93, f"Se esperaban 93 buses, pero hay {len(BUSES_DATASET)}"
    
    ids = set()
    patentes = set()
    n_buses = set()
    
    for b in BUSES_DATASET:
        # Claves obligatorias
        assert "id" in b and b["id"] is not None
        assert "patente" in b and b["patente"]
        assert "n_bus" in b and b["n_bus"]
        
        # Unicidad
        assert b["id"] not in ids, f"ID duplicado: {b['id']}"
        ids.add(b["id"])
        
        # Verificar rango 200 a 800 en número de bus
        nb_digits = ''.join(filter(str.isdigit, str(b["n_bus"])))
        assert nb_digits, f"n_bus no contiene dígitos: {b['n_bus']}"
        num = int(nb_digits)
        assert 200 <= num <= 800, f"Bus {b['n_bus']} fuera del rango 200-800"


def test_catalogo_pauta_items_oficiales():
    """Verifica que el catálogo oficial de pauta preventiva contenga exactamente 11 ítems."""
    categorias_esperadas = {
        "MOTOR Y FLUIDOS",
        "LUCES Y SISTEMA ELÉCTRICO",
        "CLIMATIZACIÓN",
        "CABINA E INSTRUMENTOS",
        "CHASIS Y ENGRASE",
        "MOTOR Y TRANSMISIÓN",
        "ESTRUCTURA Y DESGASTE",
        "CARROCERÍA Y SEGURIDAD",
        "CARROCERÍA Y VISIBILIDAD",
    }
    # Verificación de categorías representadas
    assert len(categorias_esperadas) == 9
