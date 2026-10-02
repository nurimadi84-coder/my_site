import { useCallback, useEffect, useState } from "react";
import { reportError } from "../utils/report";
import { filterProducts } from "../utils/shop";
import { ProductCard } from "./ProductCard";
import { ProductSheet } from "./ProductSheet";
import { Lightbox } from "./Lightbox";

export function ShopGrid({ limit = 0, showToolbar = false }) {
  const [products, setProducts] = useState([]);
  const [status, setStatus] = useState("Загружаем витрину…");
  const [statusHidden, setStatusHidden] = useState(false);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("new");
  const [detail, setDetail] = useState(null);
  const [lightbox, setLightbox] = useState({ images: [], index: 0 });
  const [loadError, setLoadError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadError(false);
      setStatusHidden(false);
      setStatus("Загружаем витрину…");
      try {
        const response = await fetch("/api/products");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (cancelled) return;
        if (!Array.isArray(data.products)) throw new Error("ответ без списка товаров");
        const list = data.products;
        setProducts(list);
        if (!list.length) {
          setStatusHidden(false);
          setStatus(
            limit > 0
              ? "Витрина пока пустая. Полный список — на странице всех товаров."
              : "Пока нет готовых изделий. Напишите в WhatsApp — сделаем под вашу комнату."
          );
        } else {
          setStatusHidden(true);
        }
      } catch (err) {
        if (!cancelled) {
          reportError("shop-grid", err);
          setLoadError(true);
          setStatusHidden(false);
          setStatus("Не удалось загрузить витрину. Проверьте интернет и попробуйте ещё раз — или напишите мастеру в WhatsApp.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [limit, attempt]);

  const preview = Number.isFinite(limit) && limit > 0;
  const filtered = preview ? products.slice(0, limit) : filterProducts(products, { filter, query, sort });
  const toolbarVisible = showToolbar && !preview && products.length > 0;

  useEffect(() => {
    if (!products.length) return;
    if (!filtered.length && !preview) {
      setStatusHidden(false);
      setStatus("Ничего не нашлось. Смените фильтр или поисковый запрос.");
    } else if (products.length) {
      setStatusHidden(true);
    }
  }, [filtered.length, products.length, preview, filter, query, sort]);

  const openLightbox = useCallback((images, index = 0) => {
    const list = images.filter(Boolean);
    if (!list.length) return;
    const i = ((index % list.length) + list.length) % list.length;
    setLightbox({ images: list, index: i });
  }, []);

  const stepLightbox = useCallback((delta) => {
    setLightbox((prev) => {
      if (prev.images.length < 2) return prev;
      const next = (prev.index + delta + prev.images.length) % prev.images.length;
      return { ...prev, index: next };
    });
  }, []);

  return (
    <>
      {toolbarVisible ? (
        <div className="shop-toolbar" id="shop-toolbar">
          <div className="shop-filters" id="shop-filters">
            {[
              ["all", "Все"],
              ["Шкафы", "Шкафы"],
              ["Кровати", "Кровати"],
              ["Кухни", "Кухни"],
              ["Другое", "Другое"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={`chip${filter === value ? " is-on" : ""}`}
                data-filter={value}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="shop-tools">
            <label className="shop-search">
              <span className="visually-hidden">Поиск</span>
              <input
                type="search"
                id="shop-search"
                placeholder="Найти изделие…"
                maxLength={80}
                autoComplete="off"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <label className="shop-sort">
              <span className="visually-hidden">Сортировка</span>
              <select id="shop-sort" value={sort} onChange={(e) => setSort(e.target.value)}>
                <option value="new">Сначала новые</option>
                <option value="price-asc">Цена по возрастанию</option>
                <option value="price-desc">Цена по убыванию</option>
                <option value="title">По названию</option>
              </select>
            </label>
            <a
              className="btn-download-pdf"
              href="/api/catalog/pdf"
              target="_blank"
              rel="noopener"
            >
              📄 Скачать каталог (PDF)
            </a>
          </div>
        </div>
      ) : null}

      <div className="shop-grid" id="shop-grid" data-limit={limit || undefined}>
        {filtered.map((product) => (
          <ProductCard key={product.id} product={product} onOpen={setDetail} />
        ))}
      </div>
      <p className="shop-status" id="shop-status" hidden={statusHidden} role={loadError ? "alert" : undefined}>
        {status}
        {loadError ? (
          <>
            {" "}
            <button className="btn btn--line" type="button" onClick={() => setAttempt((n) => n + 1)}>
              Повторить попытку
            </button>
          </>
        ) : null}
      </p>

      <ProductSheet
        product={detail}
        onClose={() => setDetail(null)}
        onOpenLightbox={openLightbox}
      />
      {lightbox.images.length ? (
        <Lightbox
          images={lightbox.images}
          index={lightbox.index}
          onClose={() => setLightbox({ images: [], index: 0 })}
          onStep={stepLightbox}
        />
      ) : null}
    </>
  );
}
