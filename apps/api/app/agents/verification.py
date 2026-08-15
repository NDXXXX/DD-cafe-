import re
from dataclasses import asdict, dataclass
from typing import Any

from app.agents.order_agent import OrderExecutionResult
from app.catalog.schemas import MenuItemView


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    reason: str

    def as_event(self) -> dict[str, Any]:
        return asdict(self)


def _normalize(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?]", "", text).lower()


def verify_recommendation(
    response: str,
    suggested_menu_item_id: str,
    menu: list[MenuItemView],
) -> VerificationResult:
    if not response.strip():
        return VerificationResult(False, "推荐回复为空")
    if not suggested_menu_item_id:
        return VerificationResult(True, "无 handoff 商品，跳过名称校验")
    item = next((m for m in menu if m.id == suggested_menu_item_id), None)
    if item is None:
        return VerificationResult(False, "推荐商品不在可售菜单中")
    compact = _normalize(response)
    names = [item.name, *item.aliases]
    if not any(name and _normalize(name) in compact for name in names):
        return VerificationResult(False, "推荐商品未在回复文本中出现")
    return VerificationResult(True, "推荐回复和商品 handoff 通过校验")


def verify_order_execution(result: OrderExecutionResult) -> VerificationResult:
    if not result.response.strip():
        return VerificationResult(False, "订单 Agent 回复为空")
    mutations = sum(
        value is not None for value in (result.cart, result.order, result.cancellation)
    )
    if mutations > 1:
        return VerificationResult(False, "单次请求产生了多种订单写结果")
    return VerificationResult(True, "订单结果已通过确定性服务校验")
