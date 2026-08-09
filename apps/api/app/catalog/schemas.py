from pydantic import BaseModel, ConfigDict


class MenuItemView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    category: str
    price_cents: int
    temperatures: list[str]
    tags: list[str]
    aliases: list[str]
    image_key: str
    available: bool
    featured_rank: int
