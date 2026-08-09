from typing import Any

from langgraph.config import get_stream_writer

from app.agents.state import AgentState


def emit_event(state: AgentState, event_type: str, **payload: Any) -> None:
    get_stream_writer()(
        {
            "type": event_type,
            "request_id": state["request_id"],
            **payload,
        }
    )
