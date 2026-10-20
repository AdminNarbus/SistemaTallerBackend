from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessRuleException, ConflictException, NotFoundException
from app.modules.taller.dtos.taller_ubicacion_dto import CiudadCrearDTO, TallerActualizarDTO, TallerCrearDTO
from app.modules.taller.models.taller_ubicacion import Ciudad, Taller
from app.modules.taller.repository.taller_ubicacion_repository import taller_ubicacion_repository


class TallerUbicacionCatalogoService:
    async def listar_ciudades(self, db: AsyncSession):
        return await taller_ubicacion_repository.ciudades(db)

    async def crear_ciudad(self, db: AsyncSession, dto: CiudadCrearDTO):
        codigo = dto.codigo.strip().upper()
        if await taller_ubicacion_repository.ciudad_por_codigo(db, codigo):
            raise ConflictException("Ya existe una ciudad con ese código")
        ciudad = Ciudad(codigo=codigo, nombre=dto.nombre.strip())
        db.add(ciudad)
        try:
            await db.commit()
            await db.refresh(ciudad)
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictException("Ya existe una ciudad con ese código") from exc
        return ciudad

    async def listar_talleres(self, db: AsyncSession, filtros: dict):
        return await taller_ubicacion_repository.talleres(db, filtros)

    async def crear_taller(self, db: AsyncSession, dto: TallerCrearDTO):
        if not await taller_ubicacion_repository.ciudad(db, dto.ciudad_id):
            raise NotFoundException("Ciudad no encontrada")
        taller = Taller(nombre=dto.nombre.strip(), ciudad_id=dto.ciudad_id, tipo=dto.tipo)
        db.add(taller)
        await db.commit()
        await db.refresh(taller)
        return taller

    async def actualizar_taller(self, db: AsyncSession, taller_id: int, dto: TallerActualizarDTO):
        taller = await taller_ubicacion_repository.taller(db, taller_id)
        if taller is None:
            raise NotFoundException("Taller no encontrado")
        cambios = dto.model_dump(exclude_unset=True)
        if not cambios:
            raise BusinessRuleException("Debe proporcionar al menos un campo")
        if "ciudad_id" in cambios and not await taller_ubicacion_repository.ciudad(db, cambios["ciudad_id"]):
            raise NotFoundException("Ciudad no encontrada")
        for campo, valor in cambios.items():
            setattr(taller, campo, valor.strip() if campo == "nombre" else valor)
        await db.commit()
        await db.refresh(taller)
        return taller


taller_ubicacion_catalogo_service = TallerUbicacionCatalogoService()
