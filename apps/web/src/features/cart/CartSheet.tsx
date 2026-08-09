import { Minus, Plus, Trash, X } from "@phosphor-icons/react";

import type { Cart, CartItem } from "../../shared/api/types";

interface CartSheetProps {
  cart: Cart | null;
  busyLineId: number | null;
  submitting: boolean;
  error: string;
  onClose: () => void;
  onChange: (item: CartItem, quantity: number) => void;
  onRemove: (item: CartItem) => void;
  onSubmit: () => void;
}

function money(cents: number): string {
  return `¥${(cents / 100).toFixed(2)}`;
}

export function CartSheet({
  cart,
  busyLineId,
  submitting,
  error,
  onClose,
  onChange,
  onRemove,
  onSubmit,
}: CartSheetProps) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="cart-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cart-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="sheet-header">
          <div>
            <p>提交前可修改</p>
            <h2 id="cart-title">我的购物车</h2>
          </div>
          <button className="icon-button" type="button" aria-label="关闭购物车" onClick={onClose}>
            <X size={20} />
          </button>
        </header>

        {!cart || cart.items.length === 0 ? (
          <div className="cart-empty">
            <p>购物车还是空的。</p>
            <button className="secondary-button" type="button" onClick={onClose}>
              去看看菜单
            </button>
          </div>
        ) : (
          <>
            <div className="cart-lines">
              {cart.items.map((item) => (
                <article className="cart-line" key={item.id}>
                  <div>
                    <h3>{item.name}</h3>
                    <p>
                      {item.temperature} · {money(item.unit_price_cents)}
                    </p>
                  </div>
                  <div className="quantity-control" aria-label={`${item.name}数量`}>
                    <button
                      type="button"
                      aria-label={`减少${item.name}`}
                      disabled={busyLineId === item.id}
                      onClick={() =>
                        item.quantity === 1 ? onRemove(item) : onChange(item, item.quantity - 1)
                      }
                    >
                      <Minus size={16} />
                    </button>
                    <span>{item.quantity}</span>
                    <button
                      type="button"
                      aria-label={`增加${item.name}`}
                      disabled={busyLineId === item.id || item.quantity >= 20}
                      onClick={() => onChange(item, item.quantity + 1)}
                    >
                      <Plus size={16} />
                    </button>
                    <button
                      className="trash-button"
                      type="button"
                      aria-label={`删除${item.name}`}
                      disabled={busyLineId === item.id}
                      onClick={() => onRemove(item)}
                    >
                      <Trash size={17} />
                    </button>
                  </div>
                </article>
              ))}
            </div>

            {error && <p className="inline-error">{error}</p>}
            <footer className="cart-footer">
              <div>
                <span>合计</span>
                <strong>{money(cart.total_cents)}</strong>
              </div>
              <button className="primary-button" type="button" disabled={submitting} onClick={onSubmit}>
                {submitting ? "正在提交" : "确认下单"}
              </button>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}
