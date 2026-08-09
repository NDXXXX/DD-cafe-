import { Plus } from "@phosphor-icons/react";
import { useMemo } from "react";

import type { MenuItem } from "../../shared/api/types";

const imagePositions: Record<string, string> = {
  "dd-latte": "0% 0%",
  "osmanthus-oat-latte": "50% 0%",
  "sea-salt-americano": "100% 0%",
  "yuzu-shaken-coffee": "0% 100%",
  "matcha-cloud": "50% 100%",
  "basque-cheesecake": "100% 100%",
};

interface MenuSectionProps {
  items: MenuItem[];
  loading: boolean;
  error: string;
  activeCategory: string;
  temperatures: Record<string, string>;
  addingItemId: string;
  onCategoryChange: (category: string) => void;
  onTemperatureChange: (itemId: string, temperature: string) => void;
  onAdd: (item: MenuItem) => void;
  onRetry: () => void;
}

function formatMoney(cents: number): string {
  return `¥${(cents / 100).toFixed(0)}`;
}

export function MenuSection({
  items,
  loading,
  error,
  activeCategory,
  temperatures,
  addingItemId,
  onCategoryChange,
  onTemperatureChange,
  onAdd,
  onRetry,
}: MenuSectionProps) {
  const categories = useMemo(
    () => ["推荐", ...Array.from(new Set(items.map((item) => item.category)))],
    [items],
  );
  const visibleItems =
    activeCategory === "推荐" ? items : items.filter((item) => item.category === activeCategory);

  if (loading) {
    return (
      <section className="menu-section" aria-label="菜单加载中">
        <div className="category-skeleton" />
        <div className="menu-track">
          <div className="menu-card menu-card-skeleton" />
          <div className="menu-card menu-card-skeleton" />
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="state-panel" role="alert">
        <p>{error}</p>
        <button className="secondary-button" type="button" onClick={onRetry}>
          重新加载
        </button>
      </section>
    );
  }

  if (items.length === 0) {
    return <section className="state-panel">菜单暂时为空，请稍后再来看看。</section>;
  }

  return (
    <section className="menu-section" aria-label="DD咖啡馆菜单">
      <nav className="category-nav" aria-label="菜单分类">
        {categories.map((category) => (
          <button
            className={category === activeCategory ? "category-chip is-active" : "category-chip"}
            key={category}
            type="button"
            aria-pressed={category === activeCategory}
            onClick={() => onCategoryChange(category)}
          >
            {category}
          </button>
        ))}
      </nav>

      <div className="menu-track">
        {visibleItems.map((item) => {
          const selectedTemperature = temperatures[item.id] ?? item.temperatures[0];
          return (
            <article className="menu-card" key={item.id}>
              <div
                className="menu-photo"
                role="img"
                aria-label={`${item.name} 产品照片`}
                style={{ backgroundPosition: imagePositions[item.image_key] ?? "50% 50%" }}
              />
              <div className="menu-card-body">
                <div className="menu-title-row">
                  <div>
                    <h2>{item.name}</h2>
                    <p>{item.description}</p>
                  </div>
                  <strong>{formatMoney(item.price_cents)}</strong>
                </div>

                <div className="tag-row" aria-label="商品标签">
                  {item.tags.slice(0, 3).map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>

                <div className="menu-actions">
                  <div className="temperature-control" aria-label={`${item.name}温度`}>
                    {item.temperatures.map((temperature) => (
                      <button
                        key={temperature}
                        type="button"
                        className={temperature === selectedTemperature ? "is-selected" : ""}
                        aria-pressed={temperature === selectedTemperature}
                        onClick={() => onTemperatureChange(item.id, temperature)}
                      >
                        {temperature}
                      </button>
                    ))}
                  </div>
                  <button
                    className="add-button"
                    type="button"
                    aria-label={`加入一份${item.name}`}
                    disabled={addingItemId === item.id}
                    onClick={() => onAdd(item)}
                  >
                    <Plus size={20} weight="bold" />
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
