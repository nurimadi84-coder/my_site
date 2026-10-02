export const currencyMark = {
  KZT: "₸",
  USD: "$",
  RUB: "₽",
};

export const formatPrice = (value, currency = "KZT") => {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return `${new Intl.NumberFormat("ru-RU").format(number)} ${currencyMark[currency] || "₸"}`;
};

export const money = (value, currency = "KZT") => {
  if (value === null || value === undefined || value === "") return "цена по запросу";
  return formatPrice(value, currency) || "цена по запросу";
};
