export interface MenuItem {
  id: string;
  name: string;
  description: string;
  category: string;
  price_cents: number;
  temperatures: string[];
  tags: string[];
  aliases: string[];
  image_key: string;
  available: boolean;
  featured_rank: number;
}

export interface CartItem {
  id: number;
  menu_item_id: string;
  name: string;
  quantity: number;
  temperature: string;
  unit_price_cents: number;
  line_total_cents: number;
}

export interface Cart {
  id: string;
  session_id: string;
  table_number: string;
  items: CartItem[];
  total_quantity: number;
  total_cents: number;
}

export interface OrderItem {
  menu_item_id: string;
  name: string;
  quantity: number;
  temperature: string;
  unit_price_cents: number;
  line_total_cents: number;
}

export interface Order {
  id: string;
  session_id: string;
  table_number: string;
  parent_order_id: string | null;
  status: string;
  total_cents: number;
  created_at: string;
  items: OrderItem[];
}

export type ChatEvent =
  | { type: "status"; stage: string; route?: string }
  | { type: "token"; text: string }
  | { type: "evidence"; items: unknown[] }
  | { type: "cart"; cart: Cart }
  | { type: "order"; order: Order }
  | { type: "cancellation"; cancellation: unknown }
  | { type: "done"; request_id: string }
  | { type: "error"; message: string; request_id: string };
