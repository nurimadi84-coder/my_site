import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { SITE } from "../site";
import { isValidPhone } from "../utils/phone";
import { LeadModal } from "../components/LeadModal";

export const CrmContext = createContext(null);

export function useCrm() {
  const ctx = useContext(CrmContext);
  if (!ctx) throw new Error("useCrm must be used within CrmProvider");
  return ctx;
}

const hasContact = (payload = {}) => {
  const customer = payload.customer || {};
  return String(customer.name || "").trim().length > 1 && isValidPhone(customer.phone);
};

const withContactInMessage = (message, name, phone) => {
  const base = String(message || "").trim();
  const header = [`Имя: ${name}`, `Телефон: ${phone}`].join("\n");
  if (!base) return `Здравствуйте! Хочу оформить заказ.\n\n${header}`;
  if (/^имя:/im.test(base) || /^телефон:/im.test(base)) return base;
  return `${base}\n\n${header}`;
};

const buildWaUrl = (text) =>
  `https://wa.me/${SITE.phoneE164}?text=${encodeURIComponent(text)}`;

export async function saveOrder(payload) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Не удалось сохранить заказ");
    return data.order || null;
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new Error("Сервер не ответил. Попробуйте ещё раз.");
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
}

export function CrmProvider({ children }) {
  const [leadOpen, setLeadOpen] = useState(false);
  const [leadError, setLeadError] = useState("");
  const [leadPreset, setLeadPreset] = useState({ name: "", phone: "" });
  const [busy, setBusy] = useState(false);
  const resolveLeadRef = useRef(null);
  const inFlightRef = useRef(false);

  useEffect(
    () => () => {
      document.body.classList.remove("is-lead-open");
      const cancel = resolveLeadRef.current;
      resolveLeadRef.current = null;
      if (cancel) cancel(null);
    },
    []
  );

  const askContact = useCallback((preset = {}) => {
    return new Promise((resolve) => {
      setLeadPreset({ name: preset.name || "", phone: preset.phone || "" });
      setLeadError("");
      resolveLeadRef.current = resolve;
      setLeadOpen(true);
      document.body.classList.add("is-lead-open");
    });
  }, []);

  const closeLead = useCallback(() => {
    if (busy) return;
    setLeadOpen(false);
    document.body.classList.remove("is-lead-open");
    const cancel = resolveLeadRef.current;
    resolveLeadRef.current = null;
    if (cancel) cancel(null);
  }, [busy]);

  const submitLead = useCallback((contact) => {
    setLeadOpen(false);
    document.body.classList.remove("is-lead-open");
    const done = resolveLeadRef.current;
    resolveLeadRef.current = null;
    if (done) done(contact);
  }, []);

  const showCrmError = useCallback((text) => {
    const message = String(text || "Не удалось сохранить заявку. Попробуйте ещё раз.");
    if (leadOpen) {
      setLeadError(message);
      return;
    }
    window.alert(message);
  }, [leadOpen]);

  const finishOrder = useCallback(async (payload) => {
    const message = payload.message || payload.wa_text || "";
    const customer = payload.customer || {};
    const finalMessage = withContactInMessage(message, customer.name, customer.phone);
    const finalPayload = {
      ...payload,
      customer,
      message: finalMessage,
      wa_text: finalMessage,
    };
    const waUrl = buildWaUrl(finalMessage);
    const tab = window.open("about:blank", "_blank");
    try {
      const order = await saveOrder(finalPayload);
      if (!order) throw new Error("Не удалось сохранить заказ");
      if (tab && !tab.closed) {
        tab.location.href = waUrl;
      } else {
        window.location.href = waUrl;
      }
      return { order, payload: finalPayload };
    } catch (err) {
      if (tab && !tab.closed) tab.close();
      throw err;
    }
  }, []);

  const openWhatsApp = useCallback(
    async (url, payload = {}) => {
      if (inFlightRef.current || busy) return null;
      inFlightRef.current = true;
      let next = { ...payload, customer: { ...(payload.customer || {}) } };
      try {
        if (!hasContact(next)) {
          const contact = await askContact(next.customer);
          if (!contact) return null;
          next.customer = contact;
        }
        setBusy(true);
        const message = withContactInMessage(
          next.message || next.wa_text || "",
          next.customer.name,
          next.customer.phone
        );
        next = { ...next, message, wa_text: message };
        return await finishOrder(next);
      } catch (err) {
        console.warn("CRM:", err.message || err);
        showCrmError(err.message || "Не удалось сохранить заявку. Попробуйте ещё раз.");
        return null;
      } finally {
        setBusy(false);
        inFlightRef.current = false;
      }
    },
    [askContact, busy, finishOrder, showCrmError]
  );

  const value = useMemo(
    () => ({ saveOrder, openWhatsApp, askContact }),
    [openWhatsApp, askContact]
  );

  return (
    <CrmContext.Provider value={value}>
      {children}
      <LeadModal
        open={leadOpen}
        preset={leadPreset}
        error={leadError}
        busy={busy}
        onClose={closeLead}
        onSubmit={submitLead}
        onErrorClear={() => setLeadError("")}
      />
    </CrmContext.Provider>
  );
}
