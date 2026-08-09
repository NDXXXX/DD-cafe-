from typing import Annotated

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.orders.schemas import CancellationRequestView, CartView, OrderView
from app.orders.service import OrderService

router = APIRouter(prefix="/api", tags=["orders"])
SessionDep = Annotated[Session, Depends(get_session)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=100),
]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddCartItemRequest(RequestModel):
    table_number: str = Field(min_length=1, max_length=32)
    menu_item_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=20)
    temperature: str = Field(min_length=1, max_length=20)


class ChangeCartItemRequest(RequestModel):
    quantity: int = Field(ge=1, le=20)
    temperature: str = Field(min_length=1, max_length=20)


class SubmitOrderRequest(RequestModel):
    session_id: str = Field(min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=100)
    parent_order_id: str | None = None


class CancellationRequestBody(RequestModel):
    session_id: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=500)


@router.get("/cart/{session_id}", response_model=CartView)
def get_cart(
    session_id: str,
    table_number: str,
    session: SessionDep,
) -> CartView:
    return OrderService(session).get_cart(session_id, table_number)


@router.post("/cart/{session_id}/items", response_model=CartView)
def add_cart_item(
    session_id: str,
    body: AddCartItemRequest,
    session: SessionDep,
    idempotency_key: IdempotencyKey,
) -> CartView:
    return OrderService(session).add_item(
        session_id,
        body.table_number,
        body.menu_item_id,
        body.quantity,
        body.temperature,
        idempotency_key=idempotency_key,
    )


@router.patch("/cart/{session_id}/items/{line_id}", response_model=CartView)
def change_cart_item(
    session_id: str,
    line_id: int,
    body: ChangeCartItemRequest,
    session: SessionDep,
    idempotency_key: IdempotencyKey,
) -> CartView:
    return OrderService(session).change_item(
        session_id,
        line_id,
        body.quantity,
        body.temperature,
        idempotency_key=idempotency_key,
    )


@router.delete("/cart/{session_id}/items/{line_id}", response_model=CartView)
def remove_cart_item(
    session_id: str,
    line_id: int,
    session: SessionDep,
    idempotency_key: IdempotencyKey,
) -> CartView:
    return OrderService(session).remove_item(
        session_id,
        line_id,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/orders",
    response_model=OrderView,
    status_code=status.HTTP_201_CREATED,
)
def submit_order(
    body: SubmitOrderRequest,
    session: SessionDep,
) -> OrderView:
    return OrderService(session).submit(
        body.session_id,
        body.idempotency_key,
        body.parent_order_id,
    )


@router.get("/orders/session/{session_id}", response_model=list[OrderView])
def list_orders(
    session_id: str,
    session: SessionDep,
) -> list[OrderView]:
    return OrderService(session).list_orders(session_id)


@router.post("/orders/{order_id}/cancellation", response_model=CancellationRequestView)
def request_cancellation(
    order_id: str,
    body: CancellationRequestBody,
    session: SessionDep,
) -> CancellationRequestView:
    return OrderService(session).request_cancellation(order_id, body.session_id, body.reason)
