import { createContext, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { reportError } from "../utils/report";
import { CART_KEY } from "../utils/shop";

export const CartContext = createContext(null);

function readCart() {
  try {
    const items = JSON.parse(localStorage.getItem(CART_KEY) || "[]");
    return Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : [];
  } catch {
    return [];
  }
}

function writeCart(items) {
  try {
    localStorage.setItem(CART_KEY, JSON.stringify(items));
  } catch {
    // Приватный режим или переполненное хранилище: корзина живёт до перезагрузки.
  }
}

function productImagesFirst(product) {
  if (Array.isArray(product.images) && product.images[0]) return product.images[0];
  return product.image || "";
}

function cartItemFrom(product, qty = 1) {
  return {
    id: product.id,
    title: product.title,
    price: product.price || "",
    currency: product.currency || "KZT",
    kind: product.kind || "Товар",
    category: product.category || "",
    image: product.image || productImagesFirst(product),
    qty,
  };
}

export function CartProvider({ children }) {
  const [items, setItems] = useState(() => readCart());
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const itemsRef = useRef(items);
  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  const update = useCallback((fn) => {
    setItems((prev) => {
      const next = fn(prev);
      if (next !== prev) writeCart(next);
      return next;
    });
  }, []);

  const syncWithCatalog = useCallback(async () => {
    let products;
    try {
      const response = await fetch("/api/products");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!Array.isArray(data.products)) throw new Error("ответ без списка товаров");
      products = data.products;
    } catch (err) {
      reportError("cart-sync", err);
      if (itemsRef.current.length) {
        setNotice("Не удалось сверить корзину с каталогом: цены и наличие могут быть устаревшими. Мастер уточнит их в WhatsApp.");
      }
      return;
    }
    const byId = new Map(products.map((product) => [String(product.id), product]));
    const prev = itemsRef.current;
    if (!prev.length) return;
    let removed = 0;
    let repriced = 0;
    const next = [];
    prev.forEach((item) => {
      const product = byId.get(String(item.id));
      if (!product) {
        removed += 1;
        return;
      }
      const fresh = cartItemFrom(product, item.qty || 1);
      if (String(fresh.price) !== String(item.price) || fresh.currency !== item.currency) repriced += 1;
      next.push(fresh);
    });
    const changed =
      removed || repriced || next.some((item, i) => item.title !== prev[i]?.title || item.image !== prev[i]?.image);
    if (!changed) return;
    update(() => next);
    const notes = [];
    if (removed) notes.push("часть товаров снята с продажи и убрана из корзины");
    if (repriced) notes.push("цены обновлены по каталогу");
    if (notes.length) setNotice(`Обратите внимание: ${notes.join(", ")}.`);
  }, [update]);

  useEffect(() => {
    syncWithCatalog();
  }, [syncWithCatalog]);

  useEffect(() => {
    if (open) syncWithCatalog();
    else setNotice("");
  }, [open, syncWithCatalog]);

  const addToCart = useCallback(
    (product) => {
      if (!product) return;
      update((prev) => {
        if (prev.some((item) => String(item.id) === String(product.id))) return prev;
        return [...prev, cartItemFrom(product)];
      });
    },
    [update]
  );

  const removeFromCart = useCallback(
    (id) => {
      update((prev) => prev.filter((item) => String(item.id) !== String(id)));
    },
    [update]
  );

  const clearCart = useCallback(() => {
    update(() => []);
  }, [update]);

  const isInCart = useCallback(
    (id) => items.some((item) => String(item.id) === String(id)),
    [items]
  );

  const totalQty = useMemo(
    () => items.reduce((sum, item) => sum + (item.qty || 1), 0),
    [items]
  );

  const value = useMemo(
    () => ({
      items,
      open,
      setOpen,
      notice,
      addToCart,
      removeFromCart,
      clearCart,
      isInCart,
      totalQty,
    }),
    [items, open, notice, addToCart, removeFromCart, clearCart, isInCart, totalQty]
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}
