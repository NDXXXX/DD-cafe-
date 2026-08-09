from datetime import datetime

from pydantic import BaseModel


class CartItemView(BaseModel):
    id: int
    menu_item_id: str
    name: str
    quantity: int
    temperature: str
    unit_price_cents: int
    line_total_cents: int


class CartView(BaseModel):
    id: str
    session_id: str
    table_number: str
    items: list[CartItemView]
    total_quantity: int
    total_cents: int


class OrderItemView(BaseModel):
    menu_item_id: str
    name: str
    quantity: int
    temperature: str
    unit_price_cents: int
    line_total_cents: int


class OrderView(BaseModel):
    id: str
    session_id: str
    table_number: str
    parent_order_id: str | None
    status: str
    total_cents: int
    created_at: datetime
    items: list[OrderItemView]


class CancellationRequestView(BaseModel):
    id: str
    order_id: str
    status: str
    reason: str
    created_at: datetime
