import importlib.util
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "030_ciudades_comunas_chile.py"
)
SPEC = importlib.util.spec_from_file_location("ciudades_chile_migration", MIGRATION)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_migracion_incluye_las_346_comunas_con_codigos_cut_unicos():
    comunas = MODULE.COMUNAS_CHILE
    codigos = [codigo for codigo, _ in comunas]

    assert len(comunas) == 346
    assert len(set(codigos)) == 346
    assert all(len(codigo) == 5 and codigo.isdigit() for codigo in codigos)
    assert ("01101", "Iquique") in comunas
    assert ("13101", "Santiago") in comunas
    assert ("16101", "Chillán") in comunas
    assert ("12402", "Torres del Paine") in comunas
