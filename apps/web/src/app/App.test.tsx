import { fireEvent, render, screen } from "@testing-library/react";

import { App } from "./App";

const menu = [
  {
    id: "dd-latte",
    name: "DD 拿铁",
    description: "双份浓缩与鲜牛奶",
    category: "咖啡",
    price_cents: 3200,
    temperatures: ["热", "冰"],
    tags: ["奶咖", "柔和"],
    aliases: ["拿铁"],
    image_key: "dd-latte",
    available: true,
    featured_rank: 100,
  },
];

const emptyCart = {
  id: "cart-1",
  session_id: "session-1",
  table_number: "A12",
  items: [],
  total_quantity: 0,
  total_cents: 0,
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("App", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/menu")) return jsonResponse(menu);
        if (url.includes("/api/orders/session/")) return jsonResponse([]);
        if (url.includes("/api/cart/")) return jsonResponse(emptyCart);
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads the menu and opens the conversational ordering panel", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "看菜单，也可以直接问我。" })).toBeDefined();
    expect(await screen.findByText("DD 拿铁")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: /不知道点什么/ }));

    expect(screen.getByRole("dialog", { name: "DD 点餐助手" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "购物车" })).toBeNull();
  });
});
