from dataclasses import dataclass
from enum import StrEnum


class AgentRoute(StrEnum):
    RECOMMEND = "recommend"
    ORDER = "order"
    RECOMMEND_THEN_ORDER = "recommend_then_order"
    CLARIFY = "clarify"


RECOMMENDATION_WORDS = ("推荐", "喝什么", "吃什么", "怎么选", "不知道点什么", "适合")
ORDER_WORDS = (
    "一杯",
    "两杯",
    "来一",
    "要一",
    "加入购物车",
    "加到购物车",
    "下单",
    "确认订单",
    "提交订单",
    "删掉",
    "移除",
    "不要了",
    "改成",
    "取消订单",
)
VAGUE_WRITES = ("加点东西", "随便加", "看着加", "帮我点")
RESTAURANT_QUESTION_WORDS = (
    "纸巾",
    "洗手间",
    "厕所",
    "wifi",
    "wi-fi",
    "无线网",
    "菜单",
    "营业时间",
    "营业",
    "几点",
    "停车",
    "过敏",
    "配料",
    "含奶",
    "坚果",
    "在哪",
    "怎么走",
)
EVIDENCE_REQUIRED_WORDS = tuple(
    word for word in RESTAURANT_QUESTION_WORDS if word not in {"菜单", "在哪", "怎么走"}
)


@dataclass(frozen=True)
class RouteDecision:
    route: AgentRoute
    confidence: float
    reason: str


def route_by_rules(message: str) -> RouteDecision | None:
    compact = "".join(message.split()).lower()
    has_recommendation = any(word in compact for word in RECOMMENDATION_WORDS)
    has_order = any(word in compact for word in ORDER_WORDS)
    if any(word in compact for word in VAGUE_WRITES) and not has_recommendation:
        return RouteDecision(AgentRoute.CLARIFY, 1.0, "写入意图模糊，需要补充具体商品")
    if has_recommendation and has_order:
        return RouteDecision(
            AgentRoute.RECOMMEND_THEN_ORDER,
            1.0,
            "同时包含推荐和明确购物车操作",
        )
    if has_order:
        return RouteDecision(AgentRoute.ORDER, 1.0, "包含明确的订单操作词")
    if has_recommendation:
        return RouteDecision(AgentRoute.RECOMMEND, 1.0, "包含推荐或选择需求")
    if any(word in compact for word in RESTAURANT_QUESTION_WORDS):
        return RouteDecision(AgentRoute.RECOMMEND, 0.95, "属于菜单或餐厅知识问题")
    return None


def route_intent(message: str) -> AgentRoute:
    decision = route_by_rules(message)
    return decision.route if decision is not None else AgentRoute.RECOMMEND


def requires_restaurant_evidence(message: str) -> bool:
    compact = "".join(message.split()).lower()
    return any(word in compact for word in EVIDENCE_REQUIRED_WORDS)
