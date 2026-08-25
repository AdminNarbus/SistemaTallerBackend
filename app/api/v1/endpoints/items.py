from typing import List
from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import SessionDep
from app.schemas.item import ItemCreate, ItemResponse, ItemUpdate

router = APIRouter()


@router.get("/", response_model=List[ItemResponse])
async def read_items(
    db: AsyncSession = SessionDep,
    skip: int = 0,
    limit: int = 100,
):
    """Retrieve items list."""
    items = await crud.crud_item.get_items(db, skip=skip, limit=limit)
    return items


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    item_in: ItemCreate,
    db: AsyncSession = SessionDep,
):
    """Create new item."""
    return await crud.crud_item.create_item(db=db, item_in=item_in)


@router.get("/{item_id}", response_model=ItemResponse)
async def read_item(
    item_id: int,
    db: AsyncSession = SessionDep,
):
    """Get item by ID."""
    item = await crud.crud_item.get_item(db=db, item_id=item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return item


@router.put("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    item_in: ItemUpdate,
    db: AsyncSession = SessionDep,
):
    """Update an existing item."""
    item = await crud.crud_item.get_item(db=db, item_id=item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return await crud.crud_item.update_item(db=db, db_item=item, item_in=item_in)


@router.delete("/{item_id}", response_model=ItemResponse)
async def delete_item(
    item_id: int,
    db: AsyncSession = SessionDep,
):
    """Delete an item."""
    item = await crud.crud_item.delete_item(db=db, item_id=item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return item
