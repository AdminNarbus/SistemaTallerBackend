import logging
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.modules.auth.dtos.usuario_dto import UsuarioCreateDTO
from app.modules.auth.repository.user_repository import user_repository
from app.modules.mantencion.models.categoria_falla import CategoriaFalla
from app.modules.mantencion.models.falla_taller import FallaTaller
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
from app.modules.mantencion.models.taller_solicitud_detalle import TallerSolicitudDetalle
from app.modules.buses.models.bus import Bus
from app.modules.neumaticos.models.reporte_neumatico import ReporteNeumatico
from app.modules.mantencion.models.pauta_taller import PautaTallerItem


logger = logging.getLogger(__name__)

async def seed_initial_data():
    """Sembrado de datos iniciales de prueba para el entorno de desarrollo."""
    async with AsyncSessionLocal() as db:
        try:
            # 1. Sembrar Usuarios (Exactamente uno de cada rol)
            usuarios_sembrar = [
                ("admin", "admin123", "Administrador", "Sistema", "ADMIN"),
                ("supervisor", "super123", "María", "González", "SUPERVISOR"),
                ("chofer", "chofer123", "Juan", "Pérez", "CONDUCTOR"),
                ("mecanico", "meca123", "Pedro", "Rodríguez", "MECANICO"),
            ]
            for username, password, nombre, apellido, rol in usuarios_sembrar:
                # Si ya existe con este username o con alias '1', no duplicar
                user_exists = await user_repository.get_by_username(db, username)
                if not user_exists and username in ["supervisor", "chofer", "mecanico"]:
                    user_exists = await user_repository.get_by_username(db, f"{username}1")

                if not user_exists:
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

            # 1.1 Sembrar Conductores de la flota si aún no están registrados
            from app.core.seeds.conductores_dataset import CONDUCTORES_DATASET
            from app.modules.auth.models.usuario import Usuario
            from sqlalchemy import func

            stmt_cond_count = select(func.count(Usuario.id)).where(Usuario.rol_id == 3)
            res_cond_count = await db.scalar(stmt_cond_count)
            if (res_cond_count or 0) <= 1:
                logger.info("[SEED] Sembrando %d conductores oficiales de la flota...", len(CONDUCTORES_DATASET))
                for c in CONDUCTORES_DATASET:
                    user_exists = await user_repository.get_by_username(db, c["rut"])
                    if not user_exists:
                        u_obj = Usuario(
                            nombre=c["nombre"],
                            apellido=c["apellido"],
                            username=c["rut"],
                            password_hash=c["password_hash"],
                            rol_id=3,
                            is_active=c["is_active"],
                        )
                        db.add(u_obj)
                await db.commit()
                logger.info("[SEED] %d conductores sembrados exitosamente.", len(CONDUCTORES_DATASET))

            # 2. Sembrar Categorías de Fallas
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

            # 3. Sembrar Fallas de Taller preconcebidas
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
                ("OTRO", "Avería general / Otro"),
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

            # 3.5. Sembrar catálogo de buses si la tabla está vacía
            stmt_buses_count = select(Bus)
            res_buses_count = await db.execute(stmt_buses_count)
            if not res_buses_count.scalars().first():
                from app.core.seeds.buses_dataset import BUSES_DATASET
                for b_dict in BUSES_DATASET:
                    b_obj = Bus(
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
                    db.add(b_obj)
                await db.commit()
                logger.info("[SEED] Catálogo de 93 buses de pasajeros (200-800) sincronizado exitosamente.")

            # 4. Sembrar Solicitudes de Mantención iniciales
            user_chofer = await user_repository.get_by_username(db, "chofer") or await user_repository.get_by_username(db, "chofer1")
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

            # 5. Sembrar Reporte Neumático de prueba
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

            # 6. Sembrar Catálogo de Pauta Preventiva (11 ítems oficiales)
            pauta_11_catalogo = [
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
            for p_data in pauta_11_catalogo:
                stmt_p = select(PautaTallerItem).where(PautaTallerItem.orden == p_data["orden"])
                res_p = await db.execute(stmt_p)
                p_obj = res_p.scalar_one_or_none()
                if not p_obj:
                    db.add(PautaTallerItem(**p_data))
                else:
                    p_obj.categoria = p_data["categoria"]
                    p_obj.item = p_data["item"]
                    p_obj.is_active = True

            # Eliminar respuestas e ítems obsoletos con orden > 11 si existieran
            from sqlalchemy import delete
            from app.modules.mantencion.models.pauta_taller import TallerSolicitudPauta
            await db.execute(delete(TallerSolicitudPauta).where(TallerSolicitudPauta.item_id > 11))
            await db.execute(delete(PautaTallerItem).where(PautaTallerItem.orden > 11))

            await db.commit()
            logger.info("[SEED] Catálogo de pauta preventiva de 11 ítems sincronizado exitosamente.")

        except Exception as e:
            logger.warning("[SEED] Error durante la siembra de datos de prueba: %s", e)
