"""Actualizar catálogo pauta preventiva a 10 ítems oficiales del taller

Revision ID: 015_update_pauta_items_10
Revises: 014_unificar_estados_y_estadias
Create Date: 2026-09-29 12:25:00.000000

Cambios:
- Desactiva los ítems anteriores (is_active=False)
- Inserta los 10 ítems oficiales con nomenclatura actualizada
- El catálogo pasa de 11 a 10 ítems activos

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '015_update_pauta_items_10'
down_revision: Union[str, None] = '014_unificar_estados_y_estadias'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Catálogo oficial actualizado — 10 ítems estándar de pauta preventiva de taller
ITEMS_OFICIALES_V2 = [
    {"orden": 1,  "categoria": "MOTOR Y FLUIDOS",          "item": "Control de niveles y fuga"},
    {"orden": 2,  "categoria": "LUCES Y SISTEMA ELÉCTRICO","item": "Luces exteriores"},
    {"orden": 3,  "categoria": "CLIMATIZACIÓN",            "item": "Ventilación, calefacción y A/C"},
    {"orden": 4,  "categoria": "CABINA E INSTRUMENTOS",    "item": "Tablero e indicadores"},
    {"orden": 5,  "categoria": "CHASIS Y ENGRASE",         "item": "Engrase"},
    {"orden": 6,  "categoria": "MOTOR Y TRANSMISIÓN",      "item": "Correas y rodillos"},
    {"orden": 7,  "categoria": "LUCES Y SISTEMA ELÉCTRICO","item": "Baterías y terminales"},
    {"orden": 8,  "categoria": "ESTRUCTURA Y DESGASTE",    "item": "Revisión visual neumáticos"},
    {"orden": 9,  "categoria": "CARROCERÍA Y SEGURIDAD",   "item": "Cerraduras, puertas, capó"},
    {"orden": 10, "categoria": "CARROCERÍA Y VISIBILIDAD", "item": "Parabrisas y cristales"},
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Desactivar todos los ítems activos anteriores
    conn.execute(sa.text("UPDATE pauta_taller_items SET is_active = false"))

    # 2. Insertar los 10 ítems oficiales si aún no existen con ese orden y nombre exacto
    for it in ITEMS_OFICIALES_V2:
        conn.execute(sa.text("""
            INSERT INTO pauta_taller_items (orden, categoria, item, is_active)
            SELECT :orden, :categoria, :item, true
            WHERE NOT EXISTS (
                SELECT 1 FROM pauta_taller_items
                WHERE orden = :orden AND item = :item
            )
        """), {"orden": it["orden"], "categoria": it["categoria"], "item": it["item"]})

    # 3. Reactivar los ítems con los órdenes correctos en caso de que ya existieran
    for it in ITEMS_OFICIALES_V2:
        conn.execute(sa.text("""
            UPDATE pauta_taller_items SET is_active = true
            WHERE orden = :orden AND item = :item
        """), {"orden": it["orden"], "item": it["item"]})

    # 4. Sincronizar secuencia
    conn.execute(sa.text(
        "SELECT setval('pauta_taller_items_id_seq', "
        "coalesce((SELECT max(id) FROM pauta_taller_items), 1));"
    ))


def downgrade() -> None:
    conn = op.get_bind()

    # Desactivar los ítems v2
    for it in ITEMS_OFICIALES_V2:
        conn.execute(sa.text("""
            UPDATE pauta_taller_items SET is_active = false
            WHERE orden = :orden AND item = :item
        """), {"orden": it["orden"], "item": it["item"]})

    # Reactivar los ítems v1 originales (11 ítems)
    v1_items = [
        (1, "Niveles y fugas de aceite motor"),
        (2, "Control y operación de luces exteriores"),
        (3, "Ventilación - calefacción - A/C"),
        (4, "Cuadro de instrumentos en general / Check"),
        (5, "Engrase"),
        (6, "Correas y rodillos"),
        (7, "Batería y terminales"),
        (8, "Inspección visual en cuanto a desgaste y daños"),
        (9, "Verificar estado de correas"),
        (10, "Cerraduras - pestillos - puertas - capó"),
        (11, "Revisión de parabrisas y cristales"),
    ]
    for orden, item in v1_items:
        conn.execute(sa.text("""
            UPDATE pauta_taller_items SET is_active = true
            WHERE orden = :orden AND item = :item
        """), {"orden": orden, "item": item})
