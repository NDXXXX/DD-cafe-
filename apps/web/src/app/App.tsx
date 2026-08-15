import { MapPin } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ChatDock, type ChatMessage } from "../features/assistant/ChatDock";
import { CheckInCard } from "../features/assistant/CheckInCard";
import { CartSheet } from "../features/cart/CartSheet";
import { MenuSection } from "../features/menu/MenuSection";
import { OrderBanner } from "../features/order/OrderBanner";
import {
  addCartItem,
  changeCartItem,
  createSession,
  fetchCart,
  fetchMenu,
  fetchOrders,
  removeCartItem,
  streamChat,
  submitOrder,
} from "../shared/api/client";
import type { Cart, CartItem, ChatEvent, ImageRef, MenuItem, Order } from "../shared/api/types";

function getTableNumber(): string {
  const params = new URLSearchParams(window.location.search);
  return params.get("table") || "A01";
}

function randomId(): string {
  return crypto.randomUUID();
}

function getSessionId(tableNumber: string): string {
  const key = `dd-cafe-session:${tableNumber}`;
  const stored = localStorage.getItem(key);
  if (stored) return stored;
  const created = randomId();
  localStorage.setItem(key, created);
  return created;
}

const welcomeMessage: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "你好，我可以根据口味帮你选，也可以直接把明确的商品加入购物车。",
};

interface CardState {
  imageUrl: string;
  caption: string;
  tableNumber: string;
}

export function App() {
  const tableNumber = useMemo(getTableNumber, []);
  const sessionId = useMemo(() => getSessionId(tableNumber), [tableNumber]);
  const [menu, setMenu] = useState<MenuItem[]>([]);
  const [cart, setCart] = useState<Cart | null>(null);
  const [lastOrder, setLastOrder] = useState<Order | null>(null);
  const [activeCategory, setActiveCategory] = useState("推荐");
  const [temperatures, setTemperatures] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [toast, setToast] = useState("");
  const [addingItemId, setAddingItemId] = useState("");
  const [chatOpen, setChatOpen] = useState(false);
  const [cartOpen, setCartOpen] = useState(false);
  const [chatBusy, setChatBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage]);
  const [busyLineId, setBusyLineId] = useState<number | null>(null);
  const [cartError, setCartError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [cardState, setCardState] = useState<CardState | null>(null);
  const [pendingCancellation, setPendingCancellation] = useState(false);
  const submitKeyRef = useRef("");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      await createSession(sessionId);
      const [menuItems, currentCart, orders] = await Promise.all([
        fetchMenu(),
        fetchCart(sessionId, tableNumber),
        fetchOrders(sessionId),
      ]);
      setMenu(menuItems);
      setCart(currentCart);
      setLastOrder(orders[0] ?? null);
      setTemperatures(
        Object.fromEntries(menuItems.map((item) => [item.id, item.temperatures[0]])),
      );
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "菜单加载失败");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 2200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const addItem = async (item: MenuItem) => {
    setAddingItemId(item.id);
    try {
      const updated = await addCartItem(
        sessionId,
        tableNumber,
        item.id,
        temperatures[item.id] ?? item.temperatures[0],
        randomId(),
      );
      setCart(updated);
      setToast(`${item.name} 已加入购物车`);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "加入失败");
    } finally {
      setAddingItemId("");
    }
  };

  const updateLine = async (item: CartItem, quantity: number) => {
    setBusyLineId(item.id);
    setCartError("");
    try {
      setCart(
        await changeCartItem(
          sessionId,
          item.id,
          quantity,
          item.temperature,
          randomId(),
        ),
      );
    } catch (error) {
      setCartError(error instanceof Error ? error.message : "修改失败");
    } finally {
      setBusyLineId(null);
    }
  };

  const removeLine = async (item: CartItem) => {
    setBusyLineId(item.id);
    setCartError("");
    try {
      setCart(await removeCartItem(sessionId, item.id, randomId()));
    } catch (error) {
      setCartError(error instanceof Error ? error.message : "删除失败");
    } finally {
      setBusyLineId(null);
    }
  };

  const confirmOrder = async () => {
    if (!cart || cart.items.length === 0) return;
    setSubmitting(true);
    setCartError("");
    if (!submitKeyRef.current) submitKeyRef.current = randomId();
    const idempotencyKey = submitKeyRef.current;
    try {
      const order = await submitOrder(sessionId, idempotencyKey, lastOrder?.id);
      submitKeyRef.current = "";
      setLastOrder(order);
      setPendingCancellation(false);
      setCart(await fetchCart(sessionId, tableNumber));
      setCartOpen(false);
      setToast("订单已提交");
    } catch (error) {
      setCartError(error instanceof Error ? error.message : "下单失败");
    } finally {
      setSubmitting(false);
    }
  };

  const sendMessage = async (message: string, images: ImageRef[]) => {
    if (chatBusy) return;
    if (!message.trim() && images.length === 0) return;
    setChatOpen(true);
    const requestId = randomId();
    const assistantId = `assistant-${requestId}`;
    setMessages((current) => [
      ...current,
      {
        id: `user-${requestId}`,
        role: "user",
        text: message || " ",
        images: images.length > 0 ? images : undefined,
      },
      { id: assistantId, role: "assistant", text: "" },
    ]);
    setChatBusy(true);

    const handleEvent = (event: ChatEvent) => {
      if (event.type === "token") {
        setMessages((current) =>
          current.map((item) =>
            item.id === assistantId ? { ...item, text: item.text + event.text } : item,
          ),
        );
      } else if (event.type === "cart") {
        setCart(event.cart);
      } else if (event.type === "order") {
        setLastOrder(event.order);
        setPendingCancellation(false);
        void fetchCart(sessionId, tableNumber).then(setCart);
      } else if (event.type === "cancellation") {
        setPendingCancellation(true);
      } else if (event.type === "checkin_card") {
        setMessages((current) =>
          current.map((item) =>
            item.id === assistantId
              ? {
                  ...item,
                  cardCaption: event.caption,
                  cardDescription: event.description,
                  cardImages: images,
                }
              : item,
          ),
        );
      } else if (event.type === "generated_card") {
        setCardState({
          imageUrl: `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}${event.image_url}`,
          caption: event.caption,
          tableNumber,
        });
      } else if (event.type === "error") {
        setMessages((current) =>
          current.map((item) =>
            item.id === assistantId ? { ...item, text: event.message, failed: true } : item,
          ),
        );
      }
    };

    try {
      await streamChat(
        { sessionId, tableNumber: tableNumber, requestId, message, images },
        handleEvent,
      );
    } catch (error) {
      const text = error instanceof Error ? error.message : "对话失败，请稍后重试";
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantId ? { ...item, text, failed: true } : item,
        ),
      );
    } finally {
      setChatBusy(false);
    }
  };

  const handleGenerateCard = (message: ChatMessage) => {
    const cardImages = message.cardImages ?? message.images;
    const imageUrl = cardImages?.[0]
      ? `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}${cardImages[0].url}`
      : "";
    if (!imageUrl) return;
    setCardState({
      imageUrl,
      caption: message.cardCaption ?? "今天也是被DD治愈的一天",
      tableNumber: tableNumber,
    });
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-row">
          <span className="dd-logo">DD</span>
          <div>
            <strong>DD 咖啡馆</strong>
            <small>点餐与店内助手</small>
          </div>
        </div>
        <div className="table-badge" aria-label={`${tableNumber}桌`}>
          <MapPin size={15} weight="fill" />
          {tableNumber} 桌
        </div>
      </header>

      <section className="intro-block">
        <p>今天想喝点什么？</p>
        <h1>看菜单，也可以直接问我。</h1>
        <span>告诉 DD 你的口味、预算或当下心情。</span>
      </section>

      {lastOrder && (
        <OrderBanner
          order={lastOrder}
          cancelling={pendingCancellation}
          onChatOpen={() => setChatOpen(true)}
        />
      )}

      <MenuSection
        items={menu}
        loading={loading}
        error={loadError}
        activeCategory={activeCategory}
        temperatures={temperatures}
        addingItemId={addingItemId}
        onCategoryChange={setActiveCategory}
        onTemperatureChange={(itemId, temperature) =>
          setTemperatures((current) => ({ ...current, [itemId]: temperature }))
        }
        onAdd={(item) => void addItem(item)}
        onRetry={() => void load()}
      />

      <p className="demo-note">当前为演示菜单，正式上线时替换为餐厅真实数据。</p>

      {toast && <div className="toast" role="status">{toast}</div>}

      <ChatDock
        sessionId={sessionId}
        open={chatOpen}
        cart={cart}
        messages={messages}
        busy={chatBusy}
        onOpen={() => setChatOpen(true)}
        onClose={() => setChatOpen(false)}
        onCartOpen={() => setCartOpen(true)}
        onSend={(message, images) => void sendMessage(message, images)}
        onGenerateCard={(message) => handleGenerateCard(message)}
      />

      {cartOpen && !chatOpen && (
        <CartSheet
          cart={cart}
          busyLineId={busyLineId}
          submitting={submitting}
          error={cartError}
          onClose={() => setCartOpen(false)}
          onChange={(item, quantity) => void updateLine(item, quantity)}
          onRemove={(item) => void removeLine(item)}
          onSubmit={() => void confirmOrder()}
        />
      )}

      {cardState && (
        <CheckInCard
          imageUrl={cardState.imageUrl}
          caption={cardState.caption}
          cafeName="DD 咖啡馆"
          tableNumber={cardState.tableNumber}
          onClose={() => setCardState(null)}
        />
      )}
    </main>
  );
}
