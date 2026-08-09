import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    CancellationRequestModel,
    CartItemModel,
    CartModel,
    IdempotencyRecordModel,
    MenuItemModel,
    OrderItemModel,
    OrderModel,
)
from app.orders.errors import OrderConflict, OrderNotFound, OrderValidationError
from app.orders.schemas import (
    CancellationRequestView,
    CartItemView,
    CartView,
    OrderItemView,
    OrderView,
)

MAX_ITEM_QUANTITY = 20


class OrderService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_cart(self, session_id: str, table_number: str | None = None) -> CartView:
        cart = self._find_cart(session_id)
        if cart is None:
            if table_number is None:
                raise OrderNotFound("购物车不存在")
            cart = CartModel(session_id=session_id, table_number=table_number)
            self.session.add(cart)
            self.session.commit()
            cart = self._require_cart(session_id)
        if table_number is not None and cart.table_number != table_number:
            raise OrderConflict("当前会话已经绑定其他桌号")
        return self._cart_view(cart)

    def add_item(
        self,
        session_id: str,
        table_number: str,
        menu_item_id: str,
        quantity: int,
        temperature: str,
        *,
        idempotency_key: str,
    ) -> CartView:
        operation = "add_cart_item"
        fingerprint = self._fingerprint(
            operation,
            {
                "table_number": table_number,
                "menu_item_id": menu_item_id,
                "quantity": quantity,
                "temperature": temperature,
            },
        )
        existing = self._idempotent_cart_result(
            session_id, idempotency_key, operation, fingerprint
        )
        if existing is not None:
            return existing

        self._validate_quantity(quantity)
        menu_item = self._require_available_item(menu_item_id)
        self._validate_temperature(menu_item, temperature)
        cart = self._get_or_create_cart(session_id, table_number)

        line = self.session.scalar(
            select(CartItemModel).where(
                CartItemModel.cart_id == cart.id,
                CartItemModel.menu_item_id == menu_item_id,
                CartItemModel.temperature == temperature,
            )
        )
        if line is None:
            line = CartItemModel(
                cart_id=cart.id,
                menu_item_id=menu_item_id,
                quantity=quantity,
                temperature=temperature,
                unit_price_cents=menu_item.price_cents,
            )
            self.session.add(line)
        else:
            self._validate_quantity(line.quantity + quantity)
            line.quantity += quantity
            line.unit_price_cents = menu_item.price_cents

        self.session.flush()
        result = self._cart_view(self._require_cart(session_id))
        self._record_cart_result(
            session_id, idempotency_key, operation, fingerprint, result
        )
        return self._commit_cart_result(
            session_id, idempotency_key, operation, fingerprint, result
        )

    def change_item(
        self,
        session_id: str,
        line_id: int,
        quantity: int,
        temperature: str,
        *,
        idempotency_key: str,
    ) -> CartView:
        operation = "change_cart_item"
        fingerprint = self._fingerprint(
            operation,
            {"line_id": line_id, "quantity": quantity, "temperature": temperature},
        )
        existing = self._idempotent_cart_result(
            session_id, idempotency_key, operation, fingerprint
        )
        if existing is not None:
            return existing

        self._validate_quantity(quantity)
        cart = self._require_cart(session_id)
        line = self._require_cart_line(cart, line_id)
        menu_item = self._require_available_item(line.menu_item_id)
        self._validate_temperature(menu_item, temperature)

        duplicate = self.session.scalar(
            select(CartItemModel).where(
                CartItemModel.cart_id == cart.id,
                CartItemModel.menu_item_id == line.menu_item_id,
                CartItemModel.temperature == temperature,
                CartItemModel.id != line.id,
            )
        )
        if duplicate is not None:
            self._validate_quantity(duplicate.quantity + quantity)
            duplicate.quantity += quantity
            duplicate.unit_price_cents = menu_item.price_cents
            self.session.delete(line)
        else:
            line.quantity = quantity
            line.temperature = temperature
            line.unit_price_cents = menu_item.price_cents

        self.session.flush()
        result = self._cart_view(self._require_cart(session_id))
        self._record_cart_result(
            session_id, idempotency_key, operation, fingerprint, result
        )
        return self._commit_cart_result(
            session_id, idempotency_key, operation, fingerprint, result
        )

    def remove_item(
        self,
        session_id: str,
        line_id: int,
        *,
        idempotency_key: str,
    ) -> CartView:
        operation = "remove_cart_item"
        fingerprint = self._fingerprint(operation, {"line_id": line_id})
        existing = self._idempotent_cart_result(
            session_id, idempotency_key, operation, fingerprint
        )
        if existing is not None:
            return existing

        cart = self._require_cart(session_id)
        line = self._require_cart_line(cart, line_id)
        self.session.delete(line)
        self.session.flush()
        result = self._cart_view(self._require_cart(session_id))
        self._record_cart_result(
            session_id, idempotency_key, operation, fingerprint, result
        )
        return self._commit_cart_result(
            session_id, idempotency_key, operation, fingerprint, result
        )

    def submit(
        self,
        session_id: str,
        idempotency_key: str,
        parent_order_id: str | None = None,
    ) -> OrderView:
        record_key = self._record_key(session_id, idempotency_key)
        existing_record = self.session.get(IdempotencyRecordModel, record_key)
        if existing_record is not None:
            if existing_record.operation != "submit_order":
                raise OrderConflict("幂等键已用于其他操作")
            return self.get_order(existing_record.result_id, session_id)

        cart = self._require_cart(session_id)
        if not cart.items:
            raise OrderValidationError("购物车为空，无法下单")

        if parent_order_id is not None:
            parent = self.session.get(OrderModel, parent_order_id)
            if parent is None or parent.session_id != session_id:
                raise OrderValidationError("追加单关联的原订单无效")

        order = OrderModel(
            session_id=session_id,
            table_number=cart.table_number,
            parent_order_id=parent_order_id,
            status="submitted",
            total_cents=0,
        )
        self.session.add(order)
        self.session.flush()

        total_cents = 0
        for line in list(cart.items):
            menu_item = self._require_available_item(line.menu_item_id)
            self._validate_temperature(menu_item, line.temperature)
            line_total = menu_item.price_cents * line.quantity
            total_cents += line_total
            self.session.add(
                OrderItemModel(
                    order_id=order.id,
                    menu_item_id=menu_item.id,
                    name=menu_item.name,
                    quantity=line.quantity,
                    temperature=line.temperature,
                    unit_price_cents=menu_item.price_cents,
                )
            )
            self.session.delete(line)

        order.total_cents = total_cents
        self.session.add(
            IdempotencyRecordModel(
                key=record_key,
                operation="submit_order",
                result_id=order.id,
            )
        )
        self.session.commit()
        return self.get_order(order.id, session_id)

    def get_order(self, order_id: str, session_id: str) -> OrderView:
        statement = (
            select(OrderModel)
            .where(OrderModel.id == order_id, OrderModel.session_id == session_id)
            .options(selectinload(OrderModel.items))
        )
        order = self.session.scalar(statement)
        if order is None:
            raise OrderNotFound("订单不存在")
        return self._order_view(order)

    def list_orders(self, session_id: str) -> list[OrderView]:
        statement = (
            select(OrderModel)
            .where(OrderModel.session_id == session_id)
            .options(selectinload(OrderModel.items))
            .order_by(OrderModel.created_at.desc())
        )
        return [self._order_view(order) for order in self.session.scalars(statement)]

    def request_cancellation(
        self,
        order_id: str,
        session_id: str,
        reason: str,
    ) -> CancellationRequestView:
        if not reason.strip():
            raise OrderValidationError("请填写取消原因")
        order = self.session.get(OrderModel, order_id)
        if order is None or order.session_id != session_id:
            raise OrderValidationError("不能取消其他顾客的订单")

        existing = self.session.scalar(
            select(CancellationRequestModel).where(
                CancellationRequestModel.order_id == order_id
            )
        )
        if existing is None:
            existing = CancellationRequestModel(
                order_id=order_id,
                session_id=session_id,
                reason=reason.strip(),
                status="pending",
            )
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)

        return CancellationRequestView(
            id=existing.id,
            order_id=existing.order_id,
            status=existing.status,
            reason=existing.reason,
            created_at=existing.created_at,
        )

    def _get_or_create_cart(self, session_id: str, table_number: str) -> CartModel:
        cart = self._find_cart(session_id)
        if cart is None:
            cart = CartModel(session_id=session_id, table_number=table_number)
            self.session.add(cart)
            self.session.flush()
        elif cart.table_number != table_number:
            raise OrderConflict("当前会话已经绑定其他桌号")
        return cart

    def _find_cart(self, session_id: str) -> CartModel | None:
        statement = (
            select(CartModel)
            .where(CartModel.session_id == session_id)
            .options(selectinload(CartModel.items).selectinload(CartItemModel.menu_item))
            .execution_options(populate_existing=True)
        )
        return self.session.scalar(statement)

    def _require_cart(self, session_id: str) -> CartModel:
        cart = self._find_cart(session_id)
        if cart is None:
            raise OrderNotFound("购物车不存在")
        return cart

    def _require_cart_line(self, cart: CartModel, line_id: int) -> CartItemModel:
        line = self.session.get(CartItemModel, line_id)
        if line is None or line.cart_id != cart.id:
            raise OrderNotFound("购物车商品不存在")
        return line

    def _require_available_item(self, menu_item_id: str) -> MenuItemModel:
        menu_item = self.session.get(MenuItemModel, menu_item_id)
        if menu_item is None or not menu_item.available:
            raise OrderValidationError("商品不存在或暂不可售")
        return menu_item

    def _idempotent_cart_result(
        self,
        session_id: str,
        idempotency_key: str,
        operation: str,
        fingerprint: str,
    ) -> CartView | None:
        record = self.session.get(
            IdempotencyRecordModel,
            self._record_key(session_id, idempotency_key),
        )
        if record is None:
            return None
        if record.operation != operation or record.request_fingerprint != fingerprint:
            raise OrderConflict("幂等键已用于其他订单操作")
        cart = self._require_cart(session_id)
        if cart.id != record.result_id:
            raise OrderConflict("幂等记录与当前购物车不一致")
        return self._cart_view(cart)

    def _record_cart_result(
        self,
        session_id: str,
        idempotency_key: str,
        operation: str,
        fingerprint: str,
        result: CartView,
    ) -> None:
        self.session.add(
            IdempotencyRecordModel(
                key=self._record_key(session_id, idempotency_key),
                operation=operation,
                result_id=result.id,
                request_fingerprint=fingerprint,
            )
        )

    def _commit_cart_result(
        self,
        session_id: str,
        idempotency_key: str,
        operation: str,
        fingerprint: str,
        result: CartView,
    ) -> CartView:
        try:
            self.session.commit()
            return result
        except IntegrityError:
            self.session.rollback()
            existing = self._idempotent_cart_result(
                session_id, idempotency_key, operation, fingerprint
            )
            if existing is None:
                raise
            return existing

    @staticmethod
    def _record_key(session_id: str, idempotency_key: str) -> str:
        if not idempotency_key.strip():
            raise OrderValidationError("幂等键不能为空")
        raw = f"{session_id}:{idempotency_key}"
        if len(raw) <= 180:
            return raw
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return f"{session_id}:{digest}"

    @staticmethod
    def _fingerprint(operation: str, payload: dict) -> str:
        serialized = json.dumps(
            {"operation": operation, "payload": payload},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_quantity(quantity: int) -> None:
        if quantity < 1 or quantity > MAX_ITEM_QUANTITY:
            raise OrderValidationError(f"单项数量必须在 1-{MAX_ITEM_QUANTITY} 之间")

    @staticmethod
    def _validate_temperature(menu_item: MenuItemModel, temperature: str) -> None:
        if temperature not in menu_item.temperatures:
            choices = "、".join(menu_item.temperatures)
            raise OrderValidationError(f"{menu_item.name}不支持该温度，可选：{choices}")

    @staticmethod
    def _cart_view(cart: CartModel) -> CartView:
        items = [
            CartItemView(
                id=line.id,
                menu_item_id=line.menu_item_id,
                name=line.menu_item.name,
                quantity=line.quantity,
                temperature=line.temperature,
                unit_price_cents=line.unit_price_cents,
                line_total_cents=line.unit_price_cents * line.quantity,
            )
            for line in cart.items
        ]
        return CartView(
            id=cart.id,
            session_id=cart.session_id,
            table_number=cart.table_number,
            items=items,
            total_quantity=sum(item.quantity for item in items),
            total_cents=sum(item.line_total_cents for item in items),
        )

    @staticmethod
    def _order_view(order: OrderModel) -> OrderView:
        items = [
            OrderItemView(
                menu_item_id=item.menu_item_id,
                name=item.name,
                quantity=item.quantity,
                temperature=item.temperature,
                unit_price_cents=item.unit_price_cents,
                line_total_cents=item.unit_price_cents * item.quantity,
            )
            for item in order.items
        ]
        return OrderView(
            id=order.id,
            session_id=order.session_id,
            table_number=order.table_number,
            parent_order_id=order.parent_order_id,
            status=order.status,
            total_cents=order.total_cents,
            created_at=order.created_at,
            items=items,
        )
