import { SITE } from "../site";

export const phoneDigits = (value) => String(value || "").replace(/\D/g, "");

export const normalizePhone = (value) => {
  let digits = phoneDigits(value);
  if (!digits) return "";
  if (digits.length === 10) digits = `7${digits}`;
  else if (digits.length === 11 && digits.startsWith("8")) digits = `7${digits.slice(1)}`;
  return digits;
};

/** Телефон клиента: формат +7XXXXXXXXXX и не номер самой мастерской (PHONE_E164) — по нему мастер не перезвонит. */
export const isValidPhone = (value) => {
  const digits = normalizePhone(value);
  return /^7\d{10}$/.test(digits) && digits !== SITE.phoneE164;
};

export const isShopPhone = (value) => normalizePhone(value) === SITE.phoneE164;
