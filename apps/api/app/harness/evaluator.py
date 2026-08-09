from pydantic import BaseModel, ConfigDict, Field

from app.agents.graph import AgentRuntime
from app.agents.router import AgentRoute


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    message: str
    expected_route: AgentRoute
    required_events: list[str] = Field(default_factory=list)
    forbidden_events: list[str] = Field(default_factory=list)
    expected_menu_item_id: str | None = None
    expected_temperature: str | None = None


class HarnessResult(BaseModel):
    case_id: str
    passed: bool
    expected_route: AgentRoute
    actual_route: AgentRoute
    event_types: list[str]
    failures: list[str]
    trace: list[dict]


class AgentHarness:
    def __init__(self, runtime: AgentRuntime) -> None:
        self.runtime = runtime

    async def run_case(self, case: EvalCase) -> HarnessResult:
        trace = [
            event
            async for event in self.runtime.stream(
                session_id=f"eval-{case.id}",
                table_number="EVAL",
                request_id=f"eval-request-{case.id}",
                message=case.message,
            )
        ]
        route_event = next(
            event for event in trace if event.get("stage") == "routing"
        )
        actual_route = AgentRoute(route_event["route"])
        event_types = [str(event.get("type")) for event in trace]
        failures: list[str] = []
        if actual_route != case.expected_route:
            failures.append(
                f"路由不符：期望 {case.expected_route}，实际 {actual_route}"
            )
        for event_type in case.required_events:
            if event_type not in event_types:
                failures.append(f"缺少事件：{event_type}")
        for event_type in case.forbidden_events:
            if event_type in event_types:
                failures.append(f"出现禁止事件：{event_type}")
        cart_events = [event for event in trace if event.get("type") == "cart"]
        if case.expected_menu_item_id is not None or case.expected_temperature is not None:
            items = cart_events[-1]["cart"]["items"] if cart_events else []
            if len(items) != 1:
                failures.append(f"购物车商品数量不符：期望 1，实际 {len(items)}")
            elif case.expected_menu_item_id is not None and (
                items[0]["menu_item_id"] != case.expected_menu_item_id
            ):
                failures.append(
                    "商品不符："
                    f"期望 {case.expected_menu_item_id}，实际 {items[0]['menu_item_id']}"
                )
            elif case.expected_temperature is not None and (
                items[0]["temperature"] != case.expected_temperature
            ):
                failures.append(
                    "温度不符："
                    f"期望 {case.expected_temperature}，实际 {items[0]['temperature']}"
                )
        return HarnessResult(
            case_id=case.id,
            passed=not failures,
            expected_route=case.expected_route,
            actual_route=actual_route,
            event_types=event_types,
            failures=failures,
            trace=trace,
        )
