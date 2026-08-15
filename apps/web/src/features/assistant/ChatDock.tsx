import { ArrowUp, Camera, ShoppingBag, Sparkle, X } from "@phosphor-icons/react";
import { FormEvent, useEffect, useRef, useState } from "react";

import type { Cart, ImageRef } from "../../shared/api/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  failed?: boolean;
  images?: ImageRef[];
  cardCaption?: string;
  cardDescription?: string;
  cardImages?: ImageRef[];
}

interface ChatDockProps {
  sessionId: string;
  open: boolean;
  cart: Cart | null;
  messages: ChatMessage[];
  busy: boolean;
  onOpen: () => void;
  onClose: () => void;
  onCartOpen: () => void;
  onSend: (message: string, images: ImageRef[]) => void;
  onGenerateCard: (message: ChatMessage) => void;
}

const quickPrompts = ["推荐一杯不太甜的", "来一杯拿铁", "纸巾在哪里？"];

function money(cents: number): string {
  return `¥${(cents / 100).toFixed(0)}`;
}

export function ChatDock({
  sessionId,
  open,
  cart,
  messages,
  busy,
  onOpen,
  onClose,
  onCartOpen,
  onSend,
  onGenerateCard,
}: ChatDockProps) {
  const [input, setInput] = useState("");
  const [pendingImages, setPendingImages] = useState<ImageRef[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
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
    if ((!message && pendingImages.length === 0) || busy) return;
    setInput("");
    const images = [...pendingImages];
    setPendingImages([]);
    onSend(message, images);
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    setUploadError("");
    // Import uploadImage dynamically to avoid circular dependency issues
    const { uploadImage } = await import("../../shared/api/client");
    const uploaded: ImageRef[] = [];
    let failure = "";
    for (const file of Array.from(files).slice(0, 3 - pendingImages.length)) {
      try {
        const ref = await uploadImage(sessionId, file);
        uploaded.push(ref);
      } catch (error) {
        failure = error instanceof Error ? error.message : "图片上传失败";
      }
    }
    setPendingImages((prev) => [...prev, ...uploaded].slice(0, 3));
    setUploadError(failure);
    setUploading(false);
    // Reset the file input so the same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeImage = (imageId: string) => {
    setPendingImages((prev) => prev.filter((img) => img.image_id !== imageId));
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
              <div>
                <p>{message.text || "正在整理回答…"}</p>
                {message.images && message.images.length > 0 && (
                  <div className="message-images">
                    {message.images.map((img) => (
                      <img
                        key={img.image_id}
                        src={`${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}${img.url}`}
                        alt=""
                        className="message-image-thumb"
                      />
                    ))}
                  </div>
                )}
                {message.cardDescription && <p className="card-desc">{message.cardDescription}</p>}
                {message.cardCaption && (
                  <button
                    className="card-gen-btn"
                    type="button"
                    onClick={() => onGenerateCard(message)}
                  >
                    生成打卡卡片
                  </button>
                )}
              </div>
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

        {uploadError && <p className="inline-error">{uploadError}</p>}

        {pendingImages.length > 0 && (
          <div className="image-previews" aria-label="待发送图片">
            {pendingImages.map((img) => (
              <div className="image-preview-item" key={img.image_id}>
                <img
                  src={`${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}${img.url}`}
                  alt=""
                />
                <button
                  type="button"
                  className="image-preview-remove"
                  aria-label="移除图片"
                  onClick={() => removeImage(img.image_id)}
                >
                  <X size={12} weight="bold" />
                </button>
              </div>
            ))}
            {uploading && <div className="image-preview-item uploading">上传中…</div>}
          </div>
        )}

        <div className="quick-prompts" aria-label="快捷问题">
          {quickPrompts.map((prompt) => (
            <button key={prompt} type="button" disabled={busy} onClick={() => onSend(prompt, [])}>
              {prompt}
            </button>
          ))}
        </div>

        <form className="chat-form" onSubmit={submit}>
          <label className="sr-only" htmlFor="chat-input">
            想对 DD 说什么
          </label>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            capture="environment"
            className="sr-only"
            id="image-upload"
            onChange={(e) => { void handleFileChange(e); }}
          />
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
          <button
            type="button"
            className="camera-button"
            aria-label="拍照或上传图片"
            disabled={busy || pendingImages.length >= 3}
            onClick={() => fileInputRef.current?.click()}
          >
            <Camera size={20} />
          </button>
          <button
            type="submit"
            aria-label="发送消息"
            disabled={busy || (!input.trim() && pendingImages.length === 0)}
          >
            <ArrowUp size={20} weight="bold" />
          </button>
        </form>
      </section>
    </div>
  );
}
