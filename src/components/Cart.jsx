import { useEffect } from "react";
import { formatPrice } from "../utils/money";
import { cartMessage, cartPayload, cartText } from "../utils/shop";
import { useCart } from "../hooks/useCart";
import { useCrm } from "../context/CrmContext";
import { SafeImg } from "./SafeImg";

export function CartFab({ className = "" }) {
  const { totalQty, setOpen } = useCart();
  if (!totalQty) return null;
  return (
    <button
      className={`cart-fab ${className}`.trim()}
      type="button"
      aria-label="Корзина"
      onClick={() => setOpen(true)}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M6.2 8.2h11.6l-.9 10.4a1.2 1.2 0 0 1-1.2 1.1H8.3a1.2 1.2 0 0 1-1.2-1.1L6.2 8.2z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
        <path
          d="M9 8.2V6.8a3 3 0 0 1 6 0v1.4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
      <span>{totalQty}</span>
    </button>
  );
}

export function Cart() {
  const { items, open, setOpen, notice, removeFromCart, clearCart, totalQty } = useCart();
  const { openWhatsApp } = useCrm();

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  if (!open) return null;

  const totals = new Map();
  items.forEach((item) => {
    const currency = item.currency || "KZT";
    totals.set(currency, (totals.get(currency) || 0) + (Number(item.price) || 0) * (item.qty || 1));
  });
  const unpriced = items.filter((item) => !(Number(item.price) > 0)).length;
  const totalText = [...totals]
    .filter(([, amount]) => amount)
    .map(([currency, amount]) => formatPrice(amount, currency))
    .join(" · ");

  const handleOrder = async (event) => {
    event.preventDefault();
    if (!items.length) return;
    const text = cartText(items);
    const url = cartMessage(items);
    const result = await openWhatsApp(url, cartPayload(items, text));
    if (result) {
      clearCart();
      setOpen(false);
    }
  };

  return (
    <div
      className="cart"
      onClick={(event) => {
        if (event.target === event.currentTarget) setOpen(false);
      }}
    >
      <div className="cart__panel" role="dialog" aria-label="Корзина">
        <div className="cart__head">
          <h2>Корзина</h2>
          <button className="cart__close" type="button" onClick={() => setOpen(false)}>
            Закрыть
          </button>
        </div>
        <ul className="cart__list">
          {items.length ? (
            items.map((item) => (
              <li className="cart__item" key={item.id}>
                <SafeImg src={item.image} alt="" fallback={<span className="cart__ph" />} />
                <div>
                  <h3>{item.title}</h3>
                  <p>
                    {item.qty > 1 ? `${item.qty} шт. · ` : ""}
                    {item.price ? formatPrice(item.price, item.currency) : "цена по запросу"}
                  </p>
                </div>
                <button type="button" onClick={() => removeFromCart(item.id)}>
                  Убрать
                </button>
              </li>
            ))
          ) : (
            <li className="shop-status">Корзина пустая.</li>
          )}
        </ul>
        {notice ? <p className="cart__notice" role="status">{notice}</p> : null}
        {totalText ? (
          <p className="cart__sum">
            Итого {totalText}
            {unpriced ? ` + ${unpriced} поз. по запросу` : ""}
          </p>
        ) : null}
        {totalQty > 0 ? (
          <a className="btn btn--bronze" id="cart-order" href={cartMessage(items)} onClick={handleOrder}>
            Заказать
          </a>
        ) : null}
      </div>
    </div>
  );
}
