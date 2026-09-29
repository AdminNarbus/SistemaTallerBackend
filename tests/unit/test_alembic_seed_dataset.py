import pytest
from app.core.seeds.buses_dataset import BUSES_DATASET
from app.modules.taller.models.pauta_taller import PautaTallerItem


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
    """Verifica que el catálogo oficial de pauta preventiva contenga exactamente 10 ítems."""
    from app.core.seed import PAUTA_10_CATALOGO_SEED

    assert len(PAUTA_10_CATALOGO_SEED) == 10, (
        f"Se esperaban 10 ítems en la pauta preventiva, pero hay {len(PAUTA_10_CATALOGO_SEED)}"
    )

    # Verificar que los órdenes sean del 1 al 10 sin saltos
    ordenes = sorted(it["orden"] for it in PAUTA_10_CATALOGO_SEED)
    assert ordenes == list(range(1, 11)), f"Órdenes incorrectos: {ordenes}"

    # Verificar nombres oficiales esperados
    nombres_esperados = {
        "Control de niveles y fuga",
        "Luces exteriores",
        "Ventilación, calefacción y A/C",
        "Tablero e indicadores",
        "Engrase",
        "Correas y rodillos",
        "Baterías y terminales",
        "Revisión visual neumáticos",
        "Cerraduras, puertas, capó",
        "Parabrisas y cristales",
    }
    nombres_reales = {it["item"] for it in PAUTA_10_CATALOGO_SEED}
    assert nombres_reales == nombres_esperados, (
        f"Ítems inesperados: {nombres_reales.symmetric_difference(nombres_esperados)}"
    )

    # Verificar que todos estén activos
    assert all(it["is_active"] for it in PAUTA_10_CATALOGO_SEED), "Todos los ítems deben ser is_active=True"
