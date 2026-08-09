import type { Cart, ChatEvent, MenuItem, Order } from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

interface ApiErrorBody {
  error?: { message?: string };
  detail?: string | Array<{ msg?: string }>;
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    const validationMessage = Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail;
    throw new Error(body.error?.message ?? validationMessage ?? "请求失败，请稍后重试");
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function fetchMenu(): Promise<MenuItem[]> {
  return apiRequest<MenuItem[]>("/api/menu");
}

export function fetchCart(sessionId: string, tableNumber: string): Promise<Cart> {
  const table = encodeURIComponent(tableNumber);
  return apiRequest<Cart>(`/api/cart/${sessionId}?table_number=${table}`);
}

export function addCartItem(
  sessionId: string,
  tableNumber: string,
  menuItemId: string,
  temperature: string,
  idempotencyKey: string,
): Promise<Cart> {
  return apiRequest<Cart>(`/api/cart/${sessionId}/items`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({
      table_number: tableNumber,
      menu_item_id: menuItemId,
      quantity: 1,
      temperature,
    }),
  });
}

export function changeCartItem(
  sessionId: string,
  lineId: number,
  quantity: number,
  temperature: string,
  idempotencyKey: string,
): Promise<Cart> {
  return apiRequest<Cart>(`/api/cart/${sessionId}/items/${lineId}`, {
    method: "PATCH",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ quantity, temperature }),
  });
}

export function removeCartItem(
  sessionId: string,
  lineId: number,
  idempotencyKey: string,
): Promise<Cart> {
  return apiRequest<Cart>(`/api/cart/${sessionId}/items/${lineId}`, {
    method: "DELETE",
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

export function fetchOrders(sessionId: string): Promise<Order[]> {
  return apiRequest<Order[]>(`/api/orders/session/${sessionId}`);
}

export function submitOrder(
  sessionId: string,
  idempotencyKey: string,
  parentOrderId?: string,
): Promise<Order> {
  return apiRequest<Order>("/api/orders", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      idempotency_key: idempotencyKey,
      parent_order_id: parentOrderId,
    }),
  });
}

export async function streamChat(
  input: {
    sessionId: string;
    tableNumber: string;
    requestId: string;
    message: string;
  },
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: input.sessionId,
      table_number: input.tableNumber,
      request_id: input.requestId,
      message: input.message,
    }),
  });
  if (!response.ok || response.body === null) {
    throw new Error("对话连接失败，请稍后重试");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flush = (block: string) => {
    const dataLine = block.split("\n").find((line) => line.startsWith("data: "));
    if (dataLine === undefined) return;
    onEvent(JSON.parse(dataLine.slice(6)) as ChatEvent);
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    blocks.filter(Boolean).forEach(flush);
    if (done) break;
  }
  if (buffer.trim()) flush(buffer);
}
