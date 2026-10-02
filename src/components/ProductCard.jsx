import { formatPrice } from "../utils/money";
import { orderLink, orderPayload, orderText, productImages } from "../utils/shop";
import { useCart } from "../hooks/useCart";
import { useCrm } from "../context/CrmContext";
import { PhotoPlaceholder, SafeImg } from "./SafeImg";

export function ProductCard({ product, onOpen }) {
  const { addToCart, isInCart } = useCart();
  const { openWhatsApp } = useCrm();
  const images = productImages(product);
  const inCart = isInCart(product.id);
  const desc = (product.description || "").trim();
  const short = desc.length > 90 ? `${desc.slice(0, 87)}…` : desc;

  const handleOrder = async (event) => {
    event.preventDefault();
    const text = orderText(product);
    const url = orderLink(product);
    await openWhatsApp(url, orderPayload(product, text));
  };

  return (
    <article className="product" data-category={product.category || "Другое"} data-id={product.id}>
      <button
        className="product__media"
        type="button"
        onClick={() => onOpen(product)}
        aria-label={`Открыть «${product.title}»`}
      >
        <SafeImg src={images[0]} alt={product.title} fallback={<PhotoPlaceholder />} />
        <span className="product__tag">{product.kind || "Товар"}</span>
        {images.length > 1 ? <span className="product__shots">{images.length} фото</span> : null}
      </button>
      <div className="product__body">
        <h3>
          <button type="button" onClick={() => onOpen(product)}>
            {product.title}
          </button>
        </h3>
        {short ? <p>{short}</p> : null}
        <p className="product__price">
          {product.price ? formatPrice(product.price, product.currency) : "цена по запросу"}
        </p>
        <div className="product__actions">
          <button
            className={`btn btn--line${inCart ? " is-in" : ""}`}
            type="button"
            disabled={inCart}
            aria-pressed={inCart}
            onClick={() => addToCart(product)}
          >
            {inCart ? "В корзине" : "В корзину"}
          </button>
          <a
            className="btn btn--bronze"
            href={orderLink(product)}
            target="_blank"
            rel="noopener noreferrer"
            onClick={handleOrder}
          >
            Заказать
          </a>
        </div>
      </div>
    </article>
  );
}
