from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.catalog.schemas import MenuItemView
from app.catalog.service import CatalogService

router = APIRouter(prefix="/api/menu", tags=["menu"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[MenuItemView])
def list_menu(session: SessionDep) -> list[MenuItemView]:
    return CatalogService(session).list_available()
