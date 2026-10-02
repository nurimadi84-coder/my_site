import { useEffect, useState } from "react";
import { formatPrice } from "../utils/money";
import { orderLink, orderPayload, orderText, productImages } from "../utils/shop";
import { useCart } from "../hooks/useCart";
import { useCrm } from "../context/CrmContext";
import { PhotoPlaceholder, SafeImg } from "./SafeImg";

export function ProductSheet({ product, onClose, onOpenLightbox }) {
  const { addToCart, isInCart } = useCart();
  const { openWhatsApp } = useCrm();
  const images = productImages(product);
  const [activeSrc, setActiveSrc] = useState(images[0] || "");
  const inCart = product ? isInCart(product.id) : false;

  useEffect(() => {
    setActiveSrc(images[0] || "");
  }, [product?.id]);

  useEffect(() => {
    if (!product) return undefined;
    document.body.classList.add("is-product-open");
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.classList.remove("is-product-open");
      document.removeEventListener("keydown", onKey);
    };
  }, [product, onClose]);

  if (!product) return null;

  const handleOrder = async (event) => {
    event.preventDefault();
    const text = orderText(product);
    const url = orderLink(product);
    await openWhatsApp(url, orderPayload(product, text));
  };

  return (
    <div
      className="product-sheet"
      id="product-sheet"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="product-sheet__panel" role="dialog" aria-modal="true" aria-labelledby="product-sheet-title">
        <button className="product-sheet__close" type="button" aria-label="Закрыть" onClick={onClose}>
          <svg viewBox="0 0 16 16" aria-hidden="true">
            <path
              d="M3.5 3.5 12.5 12.5M12.5 3.5 3.5 12.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </svg>
        </button>
        <div className="product-sheet__media">
          <button
            className="product-sheet__hero"
            type="button"
            id="product-sheet-hero"
            aria-label="Открыть фото"
            onClick={() => {
              if (!images.length) return;
              const index = Math.max(0, images.indexOf(activeSrc));
              onOpenLightbox(images, index);
            }}
          >
            <SafeImg
              id="product-sheet-image"
              src={activeSrc}
              alt={product.title || ""}
              fallback={<PhotoPlaceholder />}
            />
          </button>
          {images.length > 1 ? (
            <div className="product-sheet__thumbs" id="product-sheet-thumbs">
              {images.map((src, index) => (
                <button
                  key={src}
                  type="button"
                  className={src === activeSrc ? "is-on" : ""}
                  aria-label={`Фото ${index + 1}`}
                  onClick={() => setActiveSrc(src)}
                >
                  <SafeImg src={src} alt="" />
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <div className="product-sheet__body">
          <p className="product-sheet__meta">
            {[product.kind || "Товар", product.category || "Другое"].filter(Boolean).join(" · ")}
          </p>
          <h2 id="product-sheet-title">{product.title || "Изделие"}</h2>
          <p className="product-sheet__price" id="product-sheet-price">
            {product.price ? formatPrice(product.price, product.currency) : "Цена по запросу"}
          </p>
          <p className="product-sheet__text" id="product-sheet-text">
            {(product.description || "").trim() ||
              "Размеры, материалы и фурнитуру подберём под вашу комнату — уточните детали у мастера в WhatsApp."}
          </p>
          <div className="product-sheet__actions">
            <button
              className={`btn btn--line${inCart ? " is-in" : ""}`}
              type="button"
              id="product-sheet-add"
              disabled={inCart}
              onClick={() => addToCart(product)}
            >
              {inCart ? "В корзине" : "В корзину"}
            </button>
            <a
              className="btn btn--bronze"
              href={orderLink(product)}
              id="product-sheet-order"
              target="_blank"
              rel="noopener noreferrer"
              onClick={handleOrder}
            >
              Заказать
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
