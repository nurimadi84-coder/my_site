/* global __SHOP_PHONE__ */
// Номер подставляется при сборке из PHONE_E164 в .env (vite.config.js).
const phoneE164 = __SHOP_PHONE__;

export const SITE = {
  phoneDisplay: `+7 (${phoneE164.slice(1, 4)}) ${phoneE164.slice(4, 7)}-${phoneE164.slice(7, 9)}-${phoneE164.slice(9, 11)}`,
  phoneE164,
  instagram: "https://www.instagram.com/mebel_almaty2016/",
  handle: "@mebel_almaty2016",
};

export const waText = (extra) => {
  const base = "Здравствуйте! Хочу рассчитать стоимость корпусной мебели.";
  return `https://wa.me/${SITE.phoneE164}?text=${encodeURIComponent(extra || base)}`;
};

export const waUrl = (text) =>
  `https://wa.me/${SITE.phoneE164}?text=${encodeURIComponent(text)}`;
