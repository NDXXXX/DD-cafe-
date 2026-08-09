import { MapPin } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ChatDock, type ChatMessage } from "../features/assistant/ChatDock";
import { CartSheet } from "../features/cart/CartSheet";
import { MenuSection } from "../features/menu/MenuSection";
import { OrderBanner } from "../features/order/OrderBanner";
import {
  addCartItem,
  changeCartItem,
  fetchCart,
  fetchMenu,
  fetchOrders,
  removeCartItem,
  streamChat,
  submitOrder,
} from "../shared/api/client";
import type { Cart, CartItem, ChatEvent, MenuItem, Order } from "../shared/api/types";

const TABLE_NUMBER = "A12";

function randomId(): string {
  return crypto.randomUUID();
}

function getSessionId(): string {
  const stored = localStorage.getItem("dd-cafe-session");
  if (stored) return stored;
  const created = randomId();
  localStorage.setItem("dd-cafe-session", created);
  return created;
}

const welcomeMessage: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "你好，我可以根据口味帮你选，也可以直接把明确的商品加入购物车。",
};

export function App() {
  const sessionId = useMemo(getSessionId, []);
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

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [menuItems, currentCart, orders] = await Promise.all([
        fetchMenu(),
        fetchCart(sessionId, TABLE_NUMBER),
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
        TABLE_NUMBER,
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
    try {
      const order = await submitOrder(sessionId, randomId(), lastOrder?.id);
      setLastOrder(order);
      setCart(await fetchCart(sessionId, TABLE_NUMBER));
      setCartOpen(false);
      setToast("订单已提交");
    } catch (error) {
      setCartError(error instanceof Error ? error.message : "下单失败");
    } finally {
      setSubmitting(false);
    }
  };

  const sendMessage = async (message: string) => {
    if (chatBusy || !message.trim()) return;
    setChatOpen(true);
    const requestId = randomId();
    const assistantId = `assistant-${requestId}`;
    setMessages((current) => [
      ...current,
      { id: `user-${requestId}`, role: "user", text: message },
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
        void fetchCart(sessionId, TABLE_NUMBER).then(setCart);
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
        { sessionId, tableNumber: TABLE_NUMBER, requestId, message },
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
        <div className="table-badge" aria-label={`${TABLE_NUMBER}桌`}>
          <MapPin size={15} weight="fill" />
          {TABLE_NUMBER} 桌
        </div>
      </header>

      <section className="intro-block">
        <p>今天想喝点什么？</p>
        <h1>看菜单，也可以直接问我。</h1>
        <span>告诉 DD 你的口味、预算或当下心情。</span>
      </section>

      {lastOrder && <OrderBanner order={lastOrder} onChatOpen={() => setChatOpen(true)} />}

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
        open={chatOpen}
        cart={cart}
        messages={messages}
        busy={chatBusy}
        onOpen={() => setChatOpen(true)}
        onClose={() => setChatOpen(false)}
        onCartOpen={() => setCartOpen(true)}
        onSend={(message) => void sendMessage(message)}
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
    </main>
  );
}
