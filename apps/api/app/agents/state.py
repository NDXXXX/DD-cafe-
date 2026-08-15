from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class RecommendationHandoff(TypedDict):
    from_agent: str
    to_agent: str
    menu_item_id: str
    user_authorized_write: bool


class ImageAttachment(TypedDict):
    image_id: str
    local_path: str


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    session_id: str
    table_number: str
    request_id: str
    raw_user_message: str
    route: str
    route_confidence: float
    route_reason: str
    response: str
    evidence: list[dict[str, Any]]
    handoff: RecommendationHandoff | None
    verification: dict[str, Any]
    images: list[ImageAttachment]
