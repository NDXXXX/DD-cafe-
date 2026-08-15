import re
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from sqlalchemy.orm import Session

from app.catalog.schemas import MenuItemView
from app.catalog.service import CatalogService
from app.orders.errors import OrderConflict, OrderError, OrderValidationError
from app.orders.schemas import CancellationRequestView, CartView, OrderView
from app.orders.service import OrderService


class OrderAction(StrEnum):
    SUBMIT = "submit"
    CANCEL = "cancel"
    ADD = "add"
    REMOVE = "remove"
    CHANGE = "change"
    CLARIFY = "clarify"


@dataclass(frozen=True)
class OrderIntent:
    action: OrderAction
    menu_items: tuple[MenuItemView, ...] = ()
    quantity: int | None = None
    temperature: str | None = None
    source: str = "explicit"
    clarification: str = ""


@dataclass(frozen=True)
class OrderExecutionResult:
    response: str
    cart: CartView | None = None
    order: OrderView | None = None
    cancellation: CancellationRequestView | None = None


@dataclass(frozen=True)
class MenuItemMatch:
    item: MenuItemView
    token: str


class ConstrainedOrderAgent:
    quantity_words: ClassVar[dict[str, int]] = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }

    def __init__(self, session: Session) -> None:
        self.session = session
        self.catalog = CatalogService(session)
        self.orders = OrderService(session)

    def execute(
        self,
        message: str,
        session_id: str,
        table_number: str,
        request_id: str,
        suggested_menu_item_id: str | None = None,
    ) -> OrderExecutionResult:
        try:
            intent = self._parse_intent(message, suggested_menu_item_id)
            if intent.action == OrderAction.SUBMIT:
                existing_orders = self.orders.list_orders(session_id)
                parent_id = existing_orders[0].id if existing_orders else None
                order = self.orders.submit(session_id, request_id, parent_id)
                return OrderExecutionResult(
                    response=f"订单已提交，共 ¥{order.total_cents / 100:.2f}。需要纸巾或想继续加单，直接告诉我。",
                    order=order,
                )

            if intent.action == OrderAction.CANCEL:
                existing_orders = self.orders.list_orders(session_id)
                if not existing_orders:
                    raise OrderValidationError("当前没有可以申请取消的订单")
                cancellation = self.orders.request_cancellation(
                    existing_orders[0].id,
                    session_id,
                    "顾客通过对话明确申请取消",
                )
                return OrderExecutionResult(
                    response="取消申请已经提交，订单仍会保留，等待店员处理。",
                    cancellation=cancellation,
                )

            if intent.action == OrderAction.CLARIFY:
                return OrderExecutionResult(response=intent.clarification)

            if intent.action == OrderAction.REMOVE:
                return self._remove(
                    session_id,
                    table_number,
                    request_id,
                    list(intent.menu_items),
                )

            if intent.action == OrderAction.CHANGE:
                return self._change(
                    session_id,
                    table_number,
                    request_id,
                    intent,
                )

            return self._add(session_id, table_number, request_id, intent)
        except OrderError as error:
            return OrderExecutionResult(response=str(error))

    def _parse_intent(
        self,
        message: str,
        suggested_menu_item_id: str | None,
    ) -> OrderIntent:
        if suggested_menu_item_id is None and any(
            word in message for word in ("确认订单", "提交订单", "下单", "就这些")
        ):
            return OrderIntent(action=OrderAction.SUBMIT)
        if "取消订单" in message:
            return OrderIntent(action=OrderAction.CANCEL)

        menu = self.catalog.list_available()
        explicit_matches = self._match_menu_items(message, menu)
        items = [match.item for match in explicit_matches]
        source = "explicit"
        if not items and suggested_menu_item_id:
            items = [item for item in menu if item.id == suggested_menu_item_id]
            source = "recommendation_handoff"

        if any(word in message for word in ("删掉", "移除", "不要了")):
            return OrderIntent(
                action=OrderAction.REMOVE,
                menu_items=tuple(items),
                source=source,
            )
        if "改成" in message or "换成" in message:
            return OrderIntent(
                action=OrderAction.CHANGE,
                menu_items=tuple(items),
                quantity=self._quantity(message, default=None),
                temperature=self._temperature(message),
                source=source,
            )
        if not items:
            return OrderIntent(
                action=OrderAction.CLARIFY,
                clarification=(
                    "请告诉我具体商品和数量，例如“来一杯拿铁”或“加一份巴斯克”。"
                ),
            )
        if len(items) > 1:
            return OrderIntent(
                action=OrderAction.CLARIFY,
                clarification="检测到多个商品。为避免点错，请一次只确认一个商品。",
            )
        if source == "explicit":
            candidates = self._items_containing_token(explicit_matches[0].token, menu)
            if len(candidates) > 1:
                names = "、".join(item.name for item in candidates)
                return OrderIntent(
                    action=OrderAction.CLARIFY,
                    clarification=(
                        f"「{explicit_matches[0].token}」有好几款：{names}。你要哪一种？"
                    ),
                )
        return OrderIntent(
            action=OrderAction.ADD,
            menu_items=tuple(items),
            quantity=self._quantity(message),
            temperature=self._temperature(message),
            source=source,
        )

    def _add(
        self,
        session_id: str,
        table_number: str,
        request_id: str,
        intent: OrderIntent,
    ) -> OrderExecutionResult:
        item = intent.menu_items[0]
        quantity = intent.quantity or 1
        temperature = intent.temperature
        default_note = ""
        if temperature is None:
            temperature = "热" if "热" in item.temperatures else item.temperatures[0]
            if len(item.temperatures) > 1:
                default_note = f"，{item.name}按{temperature}饮"
        cart = self.orders.add_item(
            session_id,
            table_number,
            item.id,
            quantity,
            temperature,
            idempotency_key=request_id,
        )
        cart = self._verified_cart(session_id, table_number, cart)
        return OrderExecutionResult(
            response=(
                f"已加入 {quantity} 份{temperature}{item.name}{default_note}。"
                "提交前都可以修改。"
            ),
            cart=cart,
        )

    def _remove(
        self,
        session_id: str,
        table_number: str,
        request_id: str,
        matched_items: list[MenuItemView],
    ) -> OrderExecutionResult:
        cart = self.orders.get_cart(session_id, table_number)
        lines = [
            line
            for line in cart.items
            if not matched_items or line.menu_item_id in {item.id for item in matched_items}
        ]
        if not lines or (not matched_items and len(lines) > 1):
            return OrderExecutionResult(response="要删除哪一项？请说出具体商品名称。")
        for index, line in enumerate(lines):
            cart = self.orders.remove_item(
                session_id,
                line.id,
                idempotency_key=f"{request_id}:{index}",
            )
        cart = self._verified_cart(session_id, table_number, cart)
        return OrderExecutionResult(response="已从购物车移除。", cart=cart)

    def _change(
        self,
        session_id: str,
        table_number: str,
        request_id: str,
        intent: OrderIntent,
    ) -> OrderExecutionResult:
        cart = self.orders.get_cart(session_id, table_number)
        lines = [
            line
            for line in cart.items
            if not intent.menu_items
            or line.menu_item_id in {item.id for item in intent.menu_items}
        ]
        if len(lines) != 1:
            return OrderExecutionResult(response="要修改哪一项？请说出具体商品名称。")
        line = lines[0]
        quantity = intent.quantity or line.quantity
        temperature = intent.temperature or line.temperature
        updated = self.orders.change_item(
            session_id,
            line.id,
            quantity,
            temperature,
            idempotency_key=request_id,
        )
        updated = self._verified_cart(session_id, table_number, updated)
        return OrderExecutionResult(
            response=f"已把 {line.name} 改为 {temperature}，数量 {quantity}。",
            cart=updated,
        )

    def _verified_cart(
        self,
        session_id: str,
        table_number: str,
        expected: CartView,
    ) -> CartView:
        actual = self.orders.get_cart(session_id, table_number)
        if actual != expected:
            raise OrderConflict("购物车写入后回读校验失败")
        return actual

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[\s，。！？、,.!?]", "", text).lower()

    def _match_menu_items(
        self,
        message: str,
        menu: list[MenuItemView],
    ) -> list[MenuItemMatch]:
        compact = self._normalize(message)
        matches: list[tuple[int, int, MenuItemMatch]] = []
        for item in menu:
            names = sorted([item.name, *item.aliases], key=len, reverse=True)
            for name in names:
                normalized_name = self._normalize(name)
                start = compact.find(normalized_name)
                if start >= 0:
                    matches.append(
                        (start, start + len(normalized_name), MenuItemMatch(item, normalized_name))
                    )
                    break
        return [
            match
            for start, end, match in matches
            if not any(
                other.item.id != match.item.id
                and other_start <= start
                and end <= other_end
                and other_end - other_start > end - start
                for other_start, other_end, other in matches
            )
        ]

    def _items_containing_token(
        self,
        token: str,
        menu: list[MenuItemView],
    ) -> list[MenuItemView]:
        return [
            item
            for item in menu
            if any(token in self._normalize(name) for name in [item.name, *item.aliases])
        ]

    def _quantity(self, message: str, default: int | None = 1) -> int | None:
        match = re.search(r"(\d+|[一二两三四五六七八九十]+)\s*(?:杯|份|个)", message)
        if match is None:
            return default
        raw = match.group(1)
        return int(raw) if raw.isdigit() else self._chinese_quantity(raw)

    @classmethod
    def _chinese_quantity(cls, raw: str) -> int:
        if raw in cls.quantity_words:
            return cls.quantity_words[raw]
        total = 0
        for char in raw:
            digit = cls.quantity_words.get(char)
            if digit is None:
                continue
            if char == "十":
                total = total * 10 if total else 10
            else:
                total += digit
        return total

    @staticmethod
    def _temperature(message: str) -> str | None:
        if any(word in message for word in ("去冰", "少冰", "多冰", "不要冰")):
            raise OrderValidationError("当前不支持冰量选项，请选择冰、热或常温。")
        requested = set()
        if "冰" in message or "冷" in message:
            requested.add("冰")
        if "热" in message:
            requested.add("热")
        if "常温" in message:
            requested.add("常温")
        if len(requested) > 1:
            raise OrderValidationError("检测到多个温度要求，请只确认冰、热或常温中的一个。")
        return next(iter(requested), None)
