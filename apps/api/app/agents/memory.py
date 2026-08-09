from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

AGENT_RULES = (
    "推荐 Agent 只读，不得修改购物车或订单。",
    "订单 Agent 只能通过确定性 OrderService 执行写操作。",
    "用户明确说出的商品、数量和温度高于推荐 handoff。",
    "信息不足或冲突时必须询问，不得猜测后写入。",
)


def recent_history(
    messages: list[AnyMessage],
    limit: int = 6,
) -> list[tuple[str, str]]:
    history = [
        ("user" if isinstance(message, HumanMessage) else "assistant", str(message.content))
        for message in messages
        if isinstance(message, (HumanMessage, AIMessage))
    ]
    return history[-limit:]
