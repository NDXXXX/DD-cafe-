from dataclasses import asdict, dataclass
from typing import Any

from app.agents.order_agent import OrderExecutionResult


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    reason: str

    def as_event(self) -> dict[str, Any]:
        return asdict(self)


def verify_recommendation(
    response: str,
    suggested_menu_item_id: str,
    available_menu_item_ids: set[str],
) -> VerificationResult:
    if not response.strip():
        return VerificationResult(False, "推荐回复为空")
    if suggested_menu_item_id and suggested_menu_item_id not in available_menu_item_ids:
        return VerificationResult(False, "推荐商品不在可售菜单中")
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
