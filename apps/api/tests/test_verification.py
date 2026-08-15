from app.agents.verification import verify_recommendation
from app.catalog.schemas import MenuItemView


def _item(item_id: str, name: str, aliases: list[str]) -> MenuItemView:
    return MenuItemView(
        id=item_id,
        name=name,
        description="",
        category="咖啡",
        price_cents=100,
        temperatures=["热"],
        tags=[],
        aliases=aliases,
        image_key="",
        available=True,
        featured_rank=0,
    )


def test_verify_recommendation_requires_suggested_item_name_in_response() -> None:
    menu = [_item("latte", "拿铁", ["经典拿铁"])]

    assert verify_recommendation("推荐你试试拿铁", "latte", menu).passed is True
    assert verify_recommendation("推荐你试试经典拿铁", "latte", menu).passed is True
    assert verify_recommendation("今天天气不错", "latte", menu).passed is False


def test_verify_recommendation_rejects_item_not_in_menu() -> None:
    menu = [_item("latte", "拿铁", [])]

    assert verify_recommendation("推荐拿铁", "ghost", menu).passed is False


def test_verify_recommendation_allows_empty_handoff() -> None:
    assert verify_recommendation("随便聊聊", "", []).passed is True
