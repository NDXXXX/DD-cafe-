from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.schemas import MenuItemView
from app.db.models import MenuItemModel


class CatalogService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_available(self) -> list[MenuItemView]:
        statement = (
            select(MenuItemModel)
            .where(MenuItemModel.available.is_(True))
            .order_by(MenuItemModel.category, MenuItemModel.featured_rank.desc(), MenuItemModel.name)
        )
        return [MenuItemView.model_validate(item) for item in self.session.scalars(statement)]

    def get(self, menu_item_id: str) -> MenuItemModel | None:
        return self.session.get(MenuItemModel, menu_item_id)
