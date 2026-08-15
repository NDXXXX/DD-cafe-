# Agents

LangGraph orchestration for the conversational ordering assistant.

- `graph.py` — `AgentRuntime`, the parent graph that routes each turn and streams SSE events.
- `state.py` — shared `AgentState` passed between nodes.
- `events.py` — the SSE event contract (`status`, `token`, `cart`, `order`, `cancellation`, `rag_trace`, `evidence`, `verification`, `handoff`, `checkin_card`, `generated_card`, `error`, `done`).
- `router.py` — rules-first intent routing (`route_intent`), with an optional model fallback.
- `model.py` — `RecommendationModel` implementations: DeepSeek via `AsyncOpenAI`, a QwenVL multimodal reply model, and a deterministic no-key demo.
- `order_agent.py` — `ConstrainedOrderAgent`, which turns validated, structured intents into deterministic commands.
- `verification.py` — `verify_recommendation`, which checks a suggested item is actually named in the reply before a recommendation-to-order handoff.
- `memory.py` — layered short-term conversation memory.
- `vision.py`, `image_gen.py`, `image_edit.py` — multimodal models (image understanding, generation, and editing via DashScope/Qwen).
- `web_search.py` — optional real-time web search tool.
- `factory.py` — dependency wiring (checkpointer, models, runtime).

The recommendation agent is read-only and may use the menu, RAG, and web search. The order agent may only produce validated commands for the deterministic order services in `app/orders`.
