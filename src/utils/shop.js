import { formatPrice } from "./money";
import { SITE } from "../site";

export const CART_KEY = "mebel-cart";

export function productImages(product) {
  if (!product) return [];
  if (Array.isArray(product.images) && product.images.length) {
    return product.images.filter(Boolean).slice(0, 8);
  }
  return product.image ? [product.image] : [];
}

// Облегчённые копии с сервера (cards — карточки и превью, views — большой просмотр); нет копии — оригинал.
function sizedImages(product, key) {
  const sized = Array.isArray(product?.[key]) ? product[key] : [];
  return productImages(product).map((src, index) => sized[index] || src);
}

export const productCards = (product) => sizedImages(product, "cards");
export const productViews = (product) => sizedImages(product, "views");

export function orderText(product) {
  const lines = [
    "Здравствуйте! Хочу оформить заказ с сайта Mebel Almaty.",
    "",
    `Изделие: ${product.title}`,
    `Тип: ${product.kind || "Товар"}`,
    `Раздел: ${product.category || "Другое"}`,
  ];
  if (product.price) lines.push(`Цена на сайте: ${formatPrice(product.price, product.currency)}`);
  if (product.description) lines.push(`Описание: ${product.description}`);
  lines.push("", "Прошу подтвердить заказ и сроки.");
  return lines.join("\n");
}

export function orderLink(product) {
  return `https://wa.me/${SITE.phoneE164}?text=${encodeURIComponent(orderText(product))}`;
}

export function orderPayload(product, waMessage) {
  return {
    source: "product",
    items: [
      {
        id: product.id,
        title: product.title,
        price: product.price || null,
        currency: product.currency || "KZT",
        qty: 1,
        kind: product.kind || "Товар",
        category: product.category || "",
      },
    ],
    message: waMessage,
  };
}

export function cartText(items) {
  const lines = ["Здравствуйте! Хочу оформить заказ с сайта Mebel Almaty.", ""];
  items.forEach((item, index) => {
    const price = item.price ? ` — ${formatPrice(item.price, item.currency)}` : "";
    const qty = item.qty > 1 ? `, ${item.qty} шт.` : "";
    lines.push(`${index + 1}. ${item.title}${qty}${price}`);
  });
  const totals = new Map();
  items.forEach((item) => {
    const currency = item.currency || "KZT";
    totals.set(currency, (totals.get(currency) || 0) + (Number(item.price) || 0) * (item.qty || 1));
  });
  const totalLines = [...totals]
    .filter(([, sum]) => sum)
    .map(([currency, sum]) => formatPrice(sum, currency));
  if (totalLines.length) lines.push("", `Итого: ${totalLines.join(", ")}`);
  lines.push("", "Прошу подтвердить заказ и сроки.");
  return lines.join("\n");
}

export function cartMessage(items) {
  return `https://wa.me/${SITE.phoneE164}?text=${encodeURIComponent(cartText(items))}`;
}

export function cartPayload(items, waMessage) {
  return {
    source: "cart",
    items: items.map((item) => ({
      id: item.id,
      title: item.title,
      price: item.price || null,
      currency: item.currency || "KZT",
      qty: item.qty || 1,
      kind: item.kind || "Товар",
      category: item.category || "",
    })),
    message: waMessage,
  };
}

export function filterProducts(products, { filter = "all", query = "", sort = "new" } = {}) {
  const q = query.trim().toLowerCase().replace(/ё/g, "е");
  const queryParts = q.split(/\s+/).filter(Boolean);
  const stemsOf = (word) => {
    const w = String(word || "").toLowerCase().replace(/ё/g, "е");
    const out = [w];
    if (w.length > 4) out.push(w.slice(0, -1));
    if (w.length > 5) out.push(w.slice(0, -2));
    return out;
  };

  let list = products.filter((product) => {
    if (filter !== "all" && (product.category || "Другое") !== filter) return false;
    if (!queryParts.length) return true;
    const hay = `${product.title || ""} ${product.description || ""} ${product.kind || ""} ${product.category || ""}`
      .toLowerCase()
      .replace(/ё/g, "е");
    return queryParts.every((part) => stemsOf(part).some((stem) => stem && hay.includes(stem)));
  });

  const priced = (item) => {
    if (item.price === null || item.price === undefined || item.price === "") return null;
    const n = Number(item.price);
    return Number.isFinite(n) && n > 0 ? n : null;
  };

  if (sort === "price-asc") {
    list = [...list].sort((a, b) => {
      const pa = priced(a);
      const pb = priced(b);
      if (pa == null && pb == null) return 0;
      if (pa == null) return 1;
      if (pb == null) return -1;
      return pa - pb;
    });
  } else if (sort === "price-desc") {
    list = [...list].sort((a, b) => {
      const pa = priced(a);
      const pb = priced(b);
      if (pa == null && pb == null) return 0;
      if (pa == null) return 1;
      if (pb == null) return -1;
      return pb - pa;
    });
  } else if (sort === "title") {
    list = [...list].sort((a, b) => String(a.title || "").localeCompare(String(b.title || ""), "ru"));
  }
  return list;
}
