import logging
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.modules.auth.dtos.usuario_dto import UsuarioCreateDTO
from app.modules.auth.repository.user_repository import user_repository
from app.modules.buses.models.bus import Bus
from app.modules.conductores.models.conductor import Conductor
from app.modules.mantencion.models.taller_solicitud import TallerSolicitud
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
                    print(f"[SEED] Usuario '{username}' ({rol}) creado exitosamente.")

            # 2. Sembrar Buses
            buses_sembrar = [
                {"n_bus": "10", "patente": "AB1234", "marca": "Mercedes-Benz", "modelo": "O500RS"},
                {"n_bus": "301", "patente": "CD5678", "marca": "Volvo", "modelo": "B11R"},
                {"n_bus": "302", "patente": "EF9012", "marca": "Scania", "modelo": "K400"},
                {"n_bus": "500", "patente": "GH3456", "marca": "Marcopolo", "modelo": "G7 1800"},
                {"n_bus": "750", "patente": "JK7890", "marca": "Mercedes-Benz", "modelo": "Tourismo"},
                {"n_bus": "850", "patente": "LM1234", "marca": "Volvo", "modelo": "B450R"},
            ]
            for bus_data in buses_sembrar:
                stmt = select(Bus).where(Bus.n_bus == bus_data["n_bus"])
                res = await db.execute(stmt)
                bus_exist = res.scalar_one_or_none()
                if not bus_exist:
                    bus_obj = Bus(**bus_data, is_active=True)
                    db.add(bus_obj)
                    await db.commit()
                    print(f"[SEED] Bus N° {bus_data['n_bus']} ({bus_data['patente']}) creado exitosamente.")

            # 3. Sembrar Conductores
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
                    print(f"[SEED] Conductor '{cond_data['nombre']}' registrado exitosamente.")

            # 4. Sembrar Solicitudes de Mantención
            user_chofer = await user_repository.get_by_username(db, "chofer1")
            solicitudes_sembrar = [
                {
                    "n_bus": "301",
                    "descripcion": "Revisión del sistema de frenos y cambio de balatas",
                    "estado": "PENDIENTE",
                    "items": [{"sistema": "Frenos", "observacion": "Ruido inusual al frenar a alta velocidad"}],
                },
                {
                    "n_bus": "500",
                    "descripcion": "Fuga de aceite en compartimento de motor",
                    "estado": "EN_PROCESO",
                    "items": [{"sistema": "Motor", "observacion": "Goteo persistente parte posterior"}],
                },
                {
                    "n_bus": "10",
                    "descripcion": "Reemplazo de ampolletas de luces traseras",
                    "estado": "FINALIZADO",
                    "items": [{"sistema": "Eléctrico", "observacion": "Luces de freno no encienden"}],
                },
            ]
            stmt_count = select(TallerSolicitud)
            res_count = await db.execute(stmt_count)
            if not res_count.scalars().all():
                for sol_data in solicitudes_sembrar:
                    sol_obj = TallerSolicitud(
                        usuario_id=user_chofer.id if user_chofer else None,
                        **sol_data
                    )
                    db.add(sol_obj)
                await db.commit()
                print("[SEED] Solicitudes de mantención de prueba creadas exitosamente.")

            # 5. Sembrar Reporte Neumático de prueba
            stmt_neu = select(ReporteNeumatico)
            res_neu = await db.execute(stmt_neu)
            if not res_neu.scalars().all():
                bus_301 = (await db.execute(select(Bus).where(Bus.n_bus == "301"))).scalar_one_or_none()
                rep_obj = ReporteNeumatico(
                    usuario_id=user_chofer.id if user_chofer else None,
                    bus_id=bus_301.id if bus_301 else None,
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
                print("[SEED] Reporte de neumáticos de prueba creado exitosamente.")

        except Exception as e:
            print(f"[SEED ERROR] Error durante la siembra de datos de prueba: {e}")
