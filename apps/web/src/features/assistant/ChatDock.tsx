import { ArrowUp, ShoppingBag, Sparkle, X } from "@phosphor-icons/react";
import { FormEvent, useEffect, useRef, useState } from "react";

import type { Cart } from "../../shared/api/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  failed?: boolean;
}

interface ChatDockProps {
  open: boolean;
  cart: Cart | null;
  messages: ChatMessage[];
  busy: boolean;
  onOpen: () => void;
  onClose: () => void;
  onCartOpen: () => void;
  onSend: (message: string) => void;
}

const quickPrompts = ["推荐一杯不太甜的", "来一杯拿铁", "纸巾在哪里？"];

function money(cents: number): string {
  return `¥${(cents / 100).toFixed(0)}`;
}

export function ChatDock({
  open,
  cart,
  messages,
  busy,
  onOpen,
  onClose,
  onCartOpen,
  onSend,
}: ChatDockProps) {
  const [input, setInput] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const list = listRef.current;
    if (list === null) return;
    if (typeof list.scrollTo === "function") {
      list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
    } else {
      list.scrollTop = list.scrollHeight;
    }
  }, [messages, open]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    onSend(message);
  };

  if (!open) {
    return (
      <div className="bottom-dock" aria-label="点餐操作栏">
        <button className="chat-launcher" type="button" onClick={onOpen}>
          <span className="mini-logo">DD</span>
          <span>
            <strong>不知道点什么？</strong>
            <small>问问 DD</small>
          </span>
        </button>
        <button className="cart-launcher" type="button" onClick={onCartOpen}>
          <ShoppingBag size={19} />
          <strong>{cart && cart.total_cents > 0 ? money(cart.total_cents) : "购物车"}</strong>
          {cart && cart.total_quantity > 0 && <span>{cart.total_quantity}</span>}
        </button>
      </div>
    );
  }

  return (
    <div className="chat-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="chat-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="chat-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="chat-header">
          <div className="brand-row">
            <span className="dd-logo">DD</span>
            <div>
              <h2 id="chat-title">DD 点餐助手</h2>
              <p>能推荐，也能直接改购物车</p>
            </div>
          </div>
          <button className="icon-button" type="button" aria-label="关闭对话" onClick={onClose}>
            <X size={20} />
          </button>
        </header>

        <div className="message-list" ref={listRef} aria-live="polite">
          {messages.map((message) => (
            <div
              className={`message ${message.role} ${message.failed ? "is-error" : ""}`}
              key={message.id}
            >
              {message.role === "assistant" && <Sparkle size={14} weight="fill" />}
              <p>{message.text || "正在整理回答…"}</p>
            </div>
          ))}
          {busy && (
            <div className="thinking-state" aria-label="DD正在处理">
              <span />
              <span />
              <span />
            </div>
          )}
        </div>

        <div className="quick-prompts" aria-label="快捷问题">
          {quickPrompts.map((prompt) => (
            <button key={prompt} type="button" disabled={busy} onClick={() => onSend(prompt)}>
              {prompt}
            </button>
          ))}
        </div>

        <form className="chat-form" onSubmit={submit}>
          <label className="sr-only" htmlFor="chat-input">
            想对 DD 说什么
          </label>
          <textarea
            id="chat-input"
            rows={1}
            value={input}
            disabled={busy}
            placeholder="比如：想喝清爽、不太甜的"
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button type="submit" aria-label="发送消息" disabled={busy || !input.trim()}>
            <ArrowUp size={20} weight="bold" />
          </button>
        </form>
      </section>
    </div>
  );
}
