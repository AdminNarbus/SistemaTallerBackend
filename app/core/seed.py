import logging
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.modules.auth.dtos.usuario_dto import UsuarioCreateDTO
from app.modules.auth.repository.user_repository import user_repository
from app.modules.conductores.models.conductor import Conductor
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.mantencion.models.taller_solicitud_comentario import TallerSolicitudComentario
from app.modules.neumaticos.models.reporte_neumatico import ReporteNeumatico

logger = logging.getLogger(__name__)

async def seed_initial_data():
    """Sembrado de datos iniciales de prueba para el entorno de desarrollo."""
    async with AsyncSessionLocal() as db:
        try:
            # 1. Sembrar Usuarios
            usuarios_sembrar = [
                ("admin", "admin123", "Administrador", "Sistema", "ADMIN"),
                ("supervisor1", "super123", "María", "González", "SUPERVISOR"),
                ("chofer1", "chofer123", "Juan", "Pérez", "CONDUCTOR"),
                ("mecanico1", "meca123", "Pedro", "Rodríguez", "MECANICO"),
                ("mecanico2", "meca123", "Luis", "Morales", "MECANICO"),
            ]
            for username, password, nombre, apellido, rol in usuarios_sembrar:
                if not await user_repository.get_by_username(db, username):
                    await user_repository.create(
                        db,
                        UsuarioCreateDTO(
                            nombre=nombre,
                            apellido=apellido,
                            username=username,
                            password=password,
                            rol=rol,
                        ),
                    )
                    logger.info("[SEED] Usuario '%s' (%s) creado exitosamente.", username, rol)

            # 2. Sembrar Conductores
            conductores_sembrar = [
                {"nombre": "Juan Pérez", "rut": "12.345.678-9"},
                {"nombre": "Carlos Muñoz", "rut": "15.678.901-2"},
                {"nombre": "Roberto Gómez", "rut": "10.123.456-7"},
            ]
            for cond_data in conductores_sembrar:
                stmt = select(Conductor).where(Conductor.rut == cond_data["rut"])
                res = await db.execute(stmt)
                cond_exist = res.scalar_one_or_none()
                if not cond_exist:
                    cond_obj = Conductor(**cond_data)
                    db.add(cond_obj)
                    await db.commit()
                    logger.info("[SEED] Conductor '%s' registrado exitosamente.", cond_data['nombre'])

            # 3. Sembrar Categorías de Fallas
            cats_sembrar = ["FRENOS", "ELECTRICO", "MOTOR", "CARROCERIA", "CLIMATIZACION", "OTRO"]
            cat_map = {}
            for cat_nombre in cats_sembrar:
                stmt_cat = select(CategoriaFalla).where(CategoriaFalla.nombre == cat_nombre)
                res_cat = await db.execute(stmt_cat)
                cat_obj = res_cat.scalar_one_or_none()
                if not cat_obj:
                    cat_obj = CategoriaFalla(nombre=cat_nombre, is_active=True)
                    db.add(cat_obj)
                    await db.commit()
                    logger.info("[SEED] Categoría de Falla '%s' creada.", cat_nombre)
                cat_map[cat_nombre] = cat_obj.id

            # 4. Sembrar Fallas de Taller preconcebidas
            fallas_sembrar = [
                ("FRENOS", "Desgaste de balatas / pastillas"),
                ("FRENOS", "Fuga de aire en cañería de frenos"),
                ("FRENOS", "Líquido de frenos bajo"),
                ("ELECTRICO", "Luces principales o de freno quemadas"),
                ("ELECTRICO", "Batería descargada o alternador defectuoso"),
                ("MOTOR", "Fuga de aceite en carter"),
                ("MOTOR", "Sobrecalentamiento de motor"),
                ("CARROCERIA", "Empaquetadura o parabrisas agrietado"),
                ("CLIMATIZACION", "Aire acondicionado no enfría"),
            ]
            for cat_n, falla_n in fallas_sembrar:
                if cat_n in cat_map:
                    stmt_f = select(FallaTaller).where(FallaTaller.nombre == falla_n)
                    res_f = await db.execute(stmt_f)
                    if not res_f.scalar_one_or_none():
                        f_obj = FallaTaller(categoria_id=cat_map[cat_n], nombre=falla_n, is_active=True)
                        db.add(f_obj)
                        await db.commit()
                        logger.info("[SEED] Falla de Taller '%s' (%s) creada.", falla_n, cat_n)

            # 5. Sembrar Solicitudes de Mantención iniciales
            user_chofer = await user_repository.get_by_username(db, "chofer1")
            stmt_count = select(TallerSolicitud)
            res_count = await db.execute(stmt_count)
            if not res_count.scalars().all():
                # Solicitud 1: Bus 301 (REPORTADO)
                sol1 = TallerSolicitud(
                    n_bus="301",
                    usuario_creador_id=user_chofer.id if user_chofer else None,
                    estado="REPORTADO",
                    descripcion_general="Revisión urgente de sistema de frenos",
                )
                db.add(sol1)
                await db.flush()

                falla_balata = (await db.execute(select(FallaTaller).where(FallaTaller.nombre.like("%balatas%")))).scalar_one_or_none()
                det1 = TallerSolicitudDetalle(
                    solicitud_id=sol1.id,
                    falla_id=falla_balata.id if falla_balata else None,
                    descripcion_personalizada="Ruido fuerte al presionar pedal de freno",
                )
                db.add(det1)

                # Solicitud 2: Bus 500 (REPORTADO)
                sol2 = TallerSolicitud(
                    n_bus="500",
                    usuario_creador_id=user_chofer.id if user_chofer else None,
                    estado="REPORTADO",
                    descripcion_general="Luces quemadas lado izquierdo",
                )
                db.add(sol2)
                await db.flush()

                falla_luces = (await db.execute(select(FallaTaller).where(FallaTaller.nombre.like("%Luces%")))).scalar_one_or_none()
                det2 = TallerSolicitudDetalle(
                    solicitud_id=sol2.id,
                    falla_id=falla_luces.id if falla_luces else None,
                    descripcion_personalizada="Luz alta y baja del sector izquierdo apagadas",
                )
                db.add(det2)

                await db.commit()
                logger.info("[SEED] Solicitudes de mantención iniciales creadas exitosamente.")

            # 6. Sembrar Reporte Neumático de prueba
            stmt_neu = select(ReporteNeumatico)
            res_neu = await db.execute(stmt_neu)
            if not res_neu.scalars().all():
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

        except Exception as e:
            logger.warning("[SEED] Error durante la siembra de datos de prueba: %s", e)
