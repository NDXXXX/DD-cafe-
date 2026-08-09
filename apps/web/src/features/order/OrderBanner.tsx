import { CheckCircle, ChatCircleDots } from "@phosphor-icons/react";

import type { Order } from "../../shared/api/types";

interface OrderBannerProps {
  order: Order;
  onChatOpen: () => void;
}

export function OrderBanner({ order, onChatOpen }: OrderBannerProps) {
  return (
    <section className="order-banner" aria-label="订单提交成功">
      <CheckCircle size={28} weight="fill" />
      <div>
        <strong>订单已提交</strong>
        <p>尾号 {order.id.slice(-6).toUpperCase()}，还可以继续加单或询问店内事情。</p>
      </div>
      <button type="button" aria-label="继续询问DD" onClick={onChatOpen}>
        <ChatCircleDots size={20} />
      </button>
    </section>
  );
}
