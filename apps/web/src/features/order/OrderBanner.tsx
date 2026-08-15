import { CheckCircle, ChatCircleDots } from "@phosphor-icons/react";

import type { Order } from "../../shared/api/types";

interface OrderBannerProps {
  order: Order;
  cancelling?: boolean;
  onChatOpen: () => void;
}

export function OrderBanner({ order, cancelling = false, onChatOpen }: OrderBannerProps) {
  return (
    <section
      className="order-banner"
      aria-label={cancelling ? "取消申请已提交" : "订单提交成功"}
    >
      <CheckCircle size={28} weight="fill" />
      <div>
        <strong>{cancelling ? "取消申请已提交" : "订单已提交"}</strong>
        <p>
          {cancelling
            ? "订单仍会保留，等待店员处理。"
            : `尾号 ${order.id.slice(-6).toUpperCase()}，还可以继续加单或询问店内事情。`}
        </p>
      </div>
      <button type="button" aria-label="继续询问DD" onClick={onChatOpen}>
        <ChatCircleDots size={20} />
      </button>
    </section>
  );
}
