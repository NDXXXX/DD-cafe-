import type { Cart, ChatEvent, ImageRef, MenuItem, Order } from "./types";

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

function sessionToken(sessionId: string): string | null {
  return localStorage.getItem(`dd-cafe-token:${sessionId}`);
}

function authHeaders(sessionId: string): Record<string, string> {
  const token = sessionToken(sessionId);
  return token ? { "X-Session-Token": token } : {};
}

export function fetchMenu(): Promise<MenuItem[]> {
  return apiRequest<MenuItem[]>("/api/menu");
}

export async function createSession(sessionId: string): Promise<string> {
  const data = await apiRequest<{ session_id: string; token: string }>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
  localStorage.setItem(`dd-cafe-token:${sessionId}`, data.token);
  return data.token;
}

export function fetchCart(sessionId: string, tableNumber: string): Promise<Cart> {
  const table = encodeURIComponent(tableNumber);
  return apiRequest<Cart>(`/api/cart/${sessionId}?table_number=${table}`, {
    headers: authHeaders(sessionId),
  });
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
    headers: { "Idempotency-Key": idempotencyKey, ...authHeaders(sessionId) },
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
    headers: { "Idempotency-Key": idempotencyKey, ...authHeaders(sessionId) },
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
    headers: { "Idempotency-Key": idempotencyKey, ...authHeaders(sessionId) },
  });
}

export function fetchOrders(sessionId: string): Promise<Order[]> {
  return apiRequest<Order[]>(`/api/orders/session/${sessionId}`, {
    headers: authHeaders(sessionId),
  });
}

export function submitOrder(
  sessionId: string,
  idempotencyKey: string,
  parentOrderId?: string,
): Promise<Order> {
  return apiRequest<Order>("/api/orders", {
    method: "POST",
    headers: authHeaders(sessionId),
    body: JSON.stringify({
      session_id: sessionId,
      idempotency_key: idempotencyKey,
      parent_order_id: parentOrderId,
    }),
  });
}

const MAX_IMAGE_PX = 1920;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024; // 5 MB soft limit before resize

function resizeImage(file: File): Promise<Blob> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const { naturalWidth, naturalHeight } = img;
      const needsResize =
        naturalWidth > MAX_IMAGE_PX ||
        naturalHeight > MAX_IMAGE_PX ||
        file.size > MAX_IMAGE_BYTES;
      if (!needsResize) {
        resolve(file);
        return;
      }
      const scale = Math.min(
        1,
        MAX_IMAGE_PX / naturalWidth,
        MAX_IMAGE_PX / naturalHeight,
      );
      const width = Math.round(naturalWidth * scale);
      const height = Math.round(naturalHeight * scale);

      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        resolve(file);
        return;
      }
      ctx.drawImage(img, 0, 0, width, height);
      canvas.toBlob(
        (blob) => resolve(blob ?? file),
        "image/jpeg",
        0.85,
      );
    };
    img.onerror = () => resolve(file);
    img.src = URL.createObjectURL(file);
  });
}

export async function uploadImage(sessionId: string, file: File): Promise<ImageRef> {
  const compressed = await resizeImage(file);
  const formData = new FormData();
  formData.append("file", compressed, compressed instanceof File ? compressed.name : "image.jpg");
  formData.append("session_id", sessionId);
  const response = await fetch(`${API_BASE_URL}/api/images/upload`, {
    method: "POST",
    headers: authHeaders(sessionId),
    body: formData,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new Error(body.error?.message ?? "图片上传失败");
  }
  return (await response.json()) as ImageRef;
}

export async function streamChat(
  input: {
    sessionId: string;
    tableNumber: string;
    requestId: string;
    message: string;
    images?: ImageRef[];
  },
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(input.sessionId) },
    body: JSON.stringify({
      session_id: input.sessionId,
      table_number: input.tableNumber,
      request_id: input.requestId,
      message: input.message,
      images: (input.images ?? []).map((img) => ({ image_id: img.image_id })),
    }),
  });
  if (!response.ok || response.body === null) {
    throw new Error("对话连接失败，请稍后重试");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const { events, rest } = extractSseEvents(buffer);
    buffer = rest;
    events.forEach(onEvent);
    if (done) break;
  }
  const finalEvent = parseSseEvent(buffer);
  if (finalEvent) onEvent(finalEvent);
}

export function parseSseEvent(block: string): ChatEvent | null {
  const dataLine = block.split("\n").find((line) => line.startsWith("data: "));
  if (dataLine === undefined) return null;
  try {
    return JSON.parse(dataLine.slice(6)) as ChatEvent;
  } catch {
    return null;
  }
}

export function extractSseEvents(
  buffer: string,
): { events: ChatEvent[]; rest: string } {
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events = blocks
    .filter(Boolean)
    .map(parseSseEvent)
    .filter((event): event is ChatEvent => event !== null);
  return { events, rest };
}
