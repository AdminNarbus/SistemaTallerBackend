"""
seed.py
=======
Sembrado modular de datos iniciales para el entorno de desarrollo y pruebas locales.
Implementa el patrón Coordinador vs. Especialistas bajo principios SOLID (SRP/SLAP).
"""
import logging
from typing import Dict, Final, List, Tuple
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.seeds.buses_dataset import BUSES_DATASET
from app.core.seeds.conductores_dataset import CONDUCTORES_DATASET
from app.modules.auth.dtos.usuario_dto import UsuarioCreateDTO
from app.modules.auth.models.usuario import Usuario
from app.modules.auth.repository.user_repository import user_repository
from app.modules.buses.models.bus import Bus
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.pauta_taller import PautaTallerItem, TallerSolicitudPauta
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.neumaticos.models.reporte_neumatico import ReporteNeumatico

logger = logging.getLogger(__name__)

ROL_CONDUCTOR_ID: Final[int] = 3
MAX_ITEMS_PAUTA_PREVENTIVA: Final[int] = 11

USUARIOS_BASE_SEED: Final[List[Tuple[str, str, str, str, str]]] = [
    ("admin", "admin123", "Administrador", "Sistema", "ADMIN"),
    ("supervisor", "super123", "María", "González", "SUPERVISOR"),
    ("chofer", "chofer123", "Juan", "Pérez", "CONDUCTOR"),
    ("mecanico", "meca123", "Pedro", "Rodríguez", "MECANICO"),
]

CATEGORIAS_FALLAS_SEED: Final[List[str]] = [
    "FRENOS",
    "ELECTRICO",
    "MOTOR",
    "CARROCERIA",
    "CLIMATIZACION",
    "OTRO",
]

FALLAS_TALLER_SEED: Final[List[Tuple[str, str]]] = [
    ("FRENOS", "Desgaste de balatas / pastillas"),
    ("FRENOS", "Fuga de aire en cañería de frenos"),
    ("FRENOS", "Líquido de frenos bajo"),
    ("ELECTRICO", "Luces principales o de freno quemadas"),
    ("ELECTRICO", "Batería descargada o alternador defectuoso"),
    ("MOTOR", "Fuga de aceite en carter"),
    ("MOTOR", "Sobrecalentamiento de motor"),
    ("CARROCERIA", "Empaquetadura o parabrisas agrietado"),
    ("CLIMATIZACION", "Aire acondicionado no enfría"),
    ("OTRO", "Avería general / Otro"),
]

PAUTA_11_CATALOGO_SEED: Final[List[Dict[str, object]]] = [
    {"orden": 1, "categoria": "MOTOR Y FLUIDOS", "item": "Niveles y fugas de aceite motor", "is_active": True},
    {"orden": 2, "categoria": "LUCES Y SISTEMA ELÉCTRICO", "item": "Control y operación de luces exteriores", "is_active": True},
    {"orden": 3, "categoria": "CLIMATIZACIÓN", "item": "Ventilación - calefacción - A/C", "is_active": True},
    {"orden": 4, "categoria": "CABINA E INSTRUMENTOS", "item": "Cuadro de instrumentos en general / Check", "is_active": True},
    {"orden": 5, "categoria": "CHASIS Y ENGRASE", "item": "Engrase", "is_active": True},
    {"orden": 6, "categoria": "MOTOR Y TRANSMISIÓN", "item": "Correas y rodillos", "is_active": True},
    {"orden": 7, "categoria": "LUCES Y SISTEMA ELÉCTRICO", "item": "Batería y terminales", "is_active": True},
    {"orden": 8, "categoria": "ESTRUCTURA Y DESGASTE", "item": "Inspección visual en cuanto a desgaste y daños", "is_active": True},
    {"orden": 9, "categoria": "MOTOR Y TRANSMISIÓN", "item": "Verificar estado de correas", "is_active": True},
    {"orden": 10, "categoria": "CARROCERÍA Y SEGURIDAD", "item": "Cerraduras - pestillos - puertas - capó", "is_active": True},
    {"orden": 11, "categoria": "CARROCERÍA Y VISIBILIDAD", "item": "Revisión de parabrisas y cristales", "is_active": True},
]


async def _seed_usuarios(db: AsyncSession) -> None:
    """Siembra los 4 usuarios iniciales de prueba (uno por rol) si no existen."""
    for username, password, nombre, apellido, rol in USUARIOS_BASE_SEED:
        user_exists = await user_repository.get_by_username(db, username)
        if not user_exists and username in ["supervisor", "chofer", "mecanico"]:
            user_exists = await user_repository.get_by_username(db, f"{username}1")

        if not user_exists:
            dto = UsuarioCreateDTO(
                nombre=nombre,
                apellido=apellido,
                username=username,
                password=password,
                rol=rol,
            )
            await user_repository.create(db, dto)
            logger.info("[SEED] Usuario '%s' (%s) creado exitosamente.", username, rol)


async def _seed_conductores(db: AsyncSession) -> None:
    """Siembra los conductores oficiales de la flota desde el dataset estático."""
    stmt_count = select(func.count(Usuario.id)).where(Usuario.rol_id == ROL_CONDUCTOR_ID)
    res_count = await db.scalar(stmt_count)
    if (res_count or 0) > 1:
        return

    logger.info("[SEED] Sembrando %d conductores oficiales de la flota...", len(CONDUCTORES_DATASET))
    for c in CONDUCTORES_DATASET:
        if not await user_repository.get_by_username(db, c["rut"]):
            u_obj = Usuario(
                nombre=c["nombre"],
                apellido=c["apellido"],
                username=c["rut"],
                password_hash=c["password_hash"],
                rol_id=ROL_CONDUCTOR_ID,
                is_active=c["is_active"],
            )
            db.add(u_obj)
    await db.commit()
    logger.info("[SEED] %d conductores sembrados exitosamente.", len(CONDUCTORES_DATASET))


async def _seed_categorias_y_fallas(db: AsyncSession) -> Dict[str, int]:
    """Siembra el catálogo de categorías y fallas preconcebidas de taller."""
    cat_map: Dict[str, int] = {}
    for cat_nombre in CATEGORIAS_FALLAS_SEED:
        res = await db.execute(select(CategoriaFalla).where(CategoriaFalla.nombre == cat_nombre))
        cat_obj = res.scalar_one_or_none()
        if not cat_obj:
            cat_obj = CategoriaFalla(nombre=cat_nombre, is_active=True)
            db.add(cat_obj)
            await db.commit()
            logger.info("[SEED] Categoría de Falla '%s' creada.", cat_nombre)
        cat_map[cat_nombre] = cat_obj.id

    for cat_n, falla_n in FALLAS_TALLER_SEED:
        if cat_n in cat_map:
            res_f = await db.execute(select(FallaTaller).where(FallaTaller.nombre == falla_n))
            if not res_f.scalar_one_or_none():
                db.add(FallaTaller(categoria_id=cat_map[cat_n], nombre=falla_n, is_active=True))
                await db.commit()
                logger.info("[SEED] Falla de Taller '%s' (%s) creada.", falla_n, cat_n)

    return cat_map


async def _seed_catalogo_buses(db: AsyncSession) -> None:
    """Siembra el catálogo completo de buses si la tabla está vacía."""
    res_buses = await db.execute(select(Bus))
    if res_buses.scalars().first():
        return

    for b_dict in BUSES_DATASET:
        db.add(
            Bus(
                id=b_dict["id"],
                patente=b_dict["patente"],
                n_motor=b_dict.get("n_motor"),
                n_chasis=b_dict.get("n_chasis"),
                n_carroceria=b_dict.get("n_carroceria"),
                marca=b_dict.get("marca"),
                modelo=b_dict.get("modelo"),
                astos=b_dict.get("astos"),
                anio=b_dict.get("anio"),
                servicio=b_dict.get("servicio"),
                tipo_bus=b_dict.get("tipo_bus"),
                empresa_id=b_dict.get("empresa_id"),
                n_bus=b_dict.get("n_bus"),
                clasificacion=b_dict.get("clasificacion"),
                min=b_dict.get("min"),
                max=b_dict.get("max"),
                tipo=b_dict.get("tipo"),
                max_litros=b_dict.get("max_litros"),
                is_active=b_dict.get("is_active", True),
                en_taller=False,
            )
        )
    await db.commit()
    logger.info("[SEED] Catálogo de %d buses sincronizado exitosamente.", len(BUSES_DATASET))


async def _seed_solicitudes_iniciales(db: AsyncSession) -> None:
    """Siembra solicitudes iniciales de mantención para pruebas locales."""
    res_count = await db.execute(select(TallerSolicitud))
    if res_count.scalars().all():
        return

    user_chofer = await user_repository.get_by_username(db, "chofer") or await user_repository.get_by_username(db, "chofer1")
    user_id = user_chofer.id if user_chofer else None

    # Solicitud 1: Bus 301 (Frenos)
    sol1 = TallerSolicitud(
        n_bus="301",
        usuario_creador_id=user_id,
        estado="REPORTADO",
        descripcion_general="Revisión urgente de sistema de frenos",
    )
    db.add(sol1)
    await db.flush()

    res_falla1 = await db.execute(select(FallaTaller).where(FallaTaller.nombre.like("%balatas%")))
    falla_balata = res_falla1.scalar_one_or_none()
    db.add(
        TallerSolicitudDetalle(
            solicitud_id=sol1.id,
            falla_id=falla_balata.id if falla_balata else None,
            descripcion_personalizada="Ruido fuerte al presionar pedal de freno",
        )
    )

    # Solicitud 2: Bus 500 (Luces)
    sol2 = TallerSolicitud(
        n_bus="500",
        usuario_creador_id=user_id,
        estado="REPORTADO",
        descripcion_general="Luces quemadas lado izquierdo",
    )
    db.add(sol2)
    await db.flush()

    res_falla2 = await db.execute(select(FallaTaller).where(FallaTaller.nombre.like("%Luces%")))
    falla_luces = res_falla2.scalar_one_or_none()
    db.add(
        TallerSolicitudDetalle(
            solicitud_id=sol2.id,
            falla_id=falla_luces.id if falla_luces else None,
            descripcion_personalizada="Luz alta y baja del sector izquierdo apagadas",
        )
    )

    await db.commit()
    logger.info("[SEED] Solicitudes de mantención iniciales creadas exitosamente.")


async def _seed_reporte_neumatico(db: AsyncSession) -> None:
    """Siembra un reporte de neumáticos de prueba si la tabla está vacía."""
    res_neu = await db.execute(select(ReporteNeumatico))
    if res_neu.scalars().all():
        return

    user_chofer = await user_repository.get_by_username(db, "chofer") or await user_repository.get_by_username(db, "chofer1")
    rep_obj = ReporteNeumatico(
        usuario_id=user_chofer.id if user_chofer else None,
        n_bus="301",
        tipo_bus="Doble Piso",
        ruedas=[
            {"posicion": "1D", "estado": "Bueno", "presion": 110},
            {"posicion": "1I", "estado": "Regular", "presion": 105},
        ],
        motivo="Control preventivo mensual de neumáticos",
        precio=45000.0,
        marca_fuego="MF-301-A",
    )
    db.add(rep_obj)
    await db.commit()
    logger.info("[SEED] Reporte de neumáticos de prueba creado exitosamente.")


async def _seed_pauta_preventiva(db: AsyncSession) -> None:
    """Sincroniza el catálogo oficial de 11 ítems de la pauta preventiva."""
    for p_data in PAUTA_11_CATALOGO_SEED:
        res_p = await db.execute(select(PautaTallerItem).where(PautaTallerItem.orden == p_data["orden"]))
        p_obj = res_p.scalar_one_or_none()
        if not p_obj:
            db.add(PautaTallerItem(**p_data))
        else:
            p_obj.categoria = str(p_data["categoria"])
            p_obj.item = str(p_data["item"])
            p_obj.is_active = True

    # Limpieza de respuestas e ítems obsoletos fuera del catálogo de 11
    await db.execute(delete(TallerSolicitudPauta).where(TallerSolicitudPauta.item_id > MAX_ITEMS_PAUTA_PREVENTIVA))
    await db.execute(delete(PautaTallerItem).where(PautaTallerItem.orden > MAX_ITEMS_PAUTA_PREVENTIVA))
    await db.commit()
    logger.info("[SEED] Catálogo de pauta preventiva de %d ítems sincronizado.", MAX_ITEMS_PAUTA_PREVENTIVA)


async def seed_initial_data() -> None:
    """Coordinador de siembra de datos iniciales para el entorno de desarrollo."""
    async with AsyncSessionLocal() as db:
        try:
            await _seed_usuarios(db)
            await _seed_conductores(db)
            await _seed_categorias_y_fallas(db)
            await _seed_catalogo_buses(db)
            # await _seed_solicitudes_iniciales(db)  # Desactivado para mantener tabla limpia e iniciar desde OT 1
            await _seed_reporte_neumatico(db)
            await _seed_pauta_preventiva(db)
            logger.info("[SEED] Siembra de datos iniciales completada exitosamente.")
        except Exception as e:
            await db.rollback()
            logger.warning("[SEED] Error durante la siembra de datos de prueba: %s", e, exc_info=True)


__all__ = [
    "seed_initial_data",
    "ROL_CONDUCTOR_ID",
    "MAX_ITEMS_PAUTA_PREVENTIVA",
    "USUARIOS_BASE_SEED",
    "CATEGORIAS_FALLAS_SEED",
    "FALLAS_TALLER_SEED",
    "PAUTA_11_CATALOGO_SEED",
]
