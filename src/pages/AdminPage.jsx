import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { SITE } from "../site";
import { money } from "../utils/money";

const STATUS_LABEL = {
  new: "Новый",
  in_progress: "В работе",
  done: "Готово",
  cancelled: "Отменён",
};

const SOURCE_LABEL = {
  cart: "корзина",
  product: "быстрый заказ",
  calc: "заявка",
  chat: "чат",
  site: "сайт",
};

const STATUS_CLASS = {
  new: "is-new",
  in_progress: "is-progress",
  done: "is-done",
  cancelled: "is-cancelled",
};

const CATEGORIES = ["Шкафы", "Кровати", "Кухни", "Другое"];
const CURRENCIES = [
  { value: "KZT", label: "Тенге (₸)" },
  { value: "USD", label: "Доллары ($)" },
  { value: "RUB", label: "Рубли (₽)" },
];
const KINDS = ["Товар", "Услуга"];

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const NO_CONNECTION = "Нет связи с сервером. Проверьте, что сервер запущен.";
const REFRESH_FAILED = "Список не обновлён:";
let onUnauthorized = null;

async function api(url, options = {}) {
  let response;
  let text;
  try {
    response = await fetch(url, { credentials: "same-origin", ...options });
    text = await response.text();
  } catch {
    throw new ApiError(NO_CONNECTION, 0);
  }
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new ApiError(`Сервер вернул некорректный ответ (HTTP ${response.status})`, response.status);
    }
  }
  if (response.status === 401 && url !== "/api/login" && onUnauthorized) onUnauthorized();
  if (!response.ok) throw new ApiError(data.error || `Ошибка сервера (HTTP ${response.status})`, response.status);
  return data;
}

const DESK_SOURCES = [
  ["products", "/api/admin/products", "товары"],
  ["orders", "/api/admin/orders", "заказы"],
  ["clients", "/api/admin/clients", "клиенты"],
  ["chats", "/api/admin/chats", "чаты"],
];

function HealthBanner({ health }) {
  if (!health) return null;
  const problems = [];
  if (health.ai && !health.ai.key_set) problems.push("ИИ-чат не настроен: в .env пуст AI_API_KEY — посетители видят «Сервис ИИ временно недоступен».");
  else if (health.ai && health.ai.ok === false)
    problems.push(`ИИ не отвечает (${health.ai.status || "ошибка"}) с ${formatChatTime(health.ai.at)}. Посетители видят «Сервис ИИ временно недоступен».`);
  if (health.backup && health.backup.ok === false)
    problems.push(`Резервная копия не создана: ${health.backup.error || "см. logs/error.log"}.`);
  if (health.backup && health.backup.mirrors_failed?.length)
    problems.push(`Копии в облачные папки не записаны: ${health.backup.mirrors_failed.join("; ")}.`);
  (health.config_problems || []).forEach((item) => problems.push(`Настройка .env: ${item}`));
  if (!problems.length) return null;
  return (
    <div className="admin-alert" role="alert">
      <strong>Требует внимания</strong>
      <ul>
        {problems.map((text) => (
          <li key={text}>{text}</li>
        ))}
      </ul>
    </div>
  );
}

function DeskError({ error, onRetry, busy }) {
  if (!error) return null;
  return (
    <div className="admin-alert admin-alert--error" role="alert">
      <p>{error}</p>
      <button className="btn btn--bronze" type="button" onClick={onRetry} disabled={busy}>
        {busy ? "Загружаем…" : "Повторить попытку"}
      </button>
    </div>
  );
}

function formatChatTime(value) {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return String(value);
  }
}

function phoneE164(value) {
  let digits = String(value || "").replace(/\D/g, "");
  if (!digits) return "";
  if (digits.length === 10) digits = `7${digits}`;
  if (digits.startsWith("8") && digits.length === 11) digits = `7${digits.slice(1)}`;
  return digits;
}

function orderShortId(id) {
  return String(id || "").replace(/^o/, "").slice(0, 8);
}

function orderTotals(items) {
  const totals = new Map();
  (items || []).forEach((item) => {
    if (item.price === null || item.price === undefined || item.price === "") return;
    const price = Number(item.price);
    if (!Number.isFinite(price) || price <= 0) return;
    const currency = item.currency || "KZT";
    const qty = Number(item.qty) || 1;
    totals.set(currency, (totals.get(currency) || 0) + price * qty);
  });
  return [...totals].map(([currency, sum]) => money(sum, currency));
}

function orderSubject(order) {
  const items = (order.items || []).map((item) => item.title).filter(Boolean);
  if (items.length === 1) return items[0];
  if (items.length > 1) return items.slice(0, 3).join(", ");
  const note = String(order.note || "").trim();
  if (note) return note.slice(0, 80);
  return "мебель на заказ";
}

function clientWaLink(order) {
  const phone = phoneE164(order.customer?.phone);
  if (!phone) return "";
  const name = String(order.customer?.name || "").trim() || "клиент";
  const subject = orderSubject(order);
  const text = [
    `Здравствуйте, ${name}!`,
    "",
    `Вы хотели заказать у нас: ${subject}.`,
    "",
    "Это Mebel Almaty. Готовы уточнить детали, размеры и сроки — напишите, когда удобно продолжить.",
  ].join("\n");
  return `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
}

function clientCardWaLink(client) {
  const phone = phoneE164(client.phone || client.phone_key);
  if (!phone) return "";
  const name = String(client.name || "").trim() || "клиент";
  const text = [
    `Здравствуйте, ${name}!`,
    "",
    "Вы хотели заказать у нас мебель.",
    "",
    "Это Mebel Almaty. Готовы уточнить детали и сроки — напишите, когда удобно продолжить.",
  ].join("\n");
  return `https://wa.me/${phone}?text=${encodeURIComponent(text)}`;
}

function clientMetaLine(client) {
  const count = Number(client.orders_count) || 0;
  if (!count) return "заказов пока нет";
  const when = formatChatTime(client.last_order_at || client.updated_at);
  return when ? `последний заказ ${when}` : "есть заказы";
}

function shrinkPhoto(file) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => {
      const max = 1600;
      const scale = Math.min(1, max / Math.max(image.width, image.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(image.width * scale);
      canvas.height = Math.round(image.height * scale);
      canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) => {
          URL.revokeObjectURL(url);
          if (!blob) reject(new Error("Не удалось подготовить фото"));
          else resolve(blob);
        },
        "image/jpeg",
        0.84
      );
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Это не фотография"));
    };
    image.src = url;
  });
}

async function uploadPhoto(file) {
  const blob = await shrinkPhoto(file);
  const response = await fetch("/api/upload", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "image/jpeg" },
    body: blob,
  });
  const data = await response.json().catch(() => null);
  if (!data) throw new Error(`Фото не загрузилось: сервер вернул некорректный ответ (HTTP ${response.status})`);
  if (!response.ok) throw new Error(data.error || "Фото не загрузилось");
  return data.image;
}

function Pick({ name, labelId, options, value, onChange }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const selected = options.find((o) => o.value === value) || options[0];

  useEffect(() => {
    const onDoc = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("click", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  return (
    <div className={`pick${open ? " is-open" : ""}`} data-pick ref={rootRef}>
      <select
        className="pick__native"
        name={name}
        tabIndex={-1}
        aria-hidden="true"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <button
        className="pick__btn"
        type="button"
        aria-labelledby={labelId}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="pick__value">{selected?.label}</span>
        <svg className="pick__chevron" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M3.5 6.2 8 10.4l4.5-4.2" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <ul className="pick__list" role="listbox" hidden={!open}>
        {options.map((opt) => (
          <li key={opt.value} role="presentation">
            <button
              type="button"
              role="option"
              className={opt.value === value ? "is-on" : ""}
              aria-selected={opt.value === value}
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
            >
              {opt.label}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

const emptyForm = () => ({
  id: "",
  title: "",
  category: "Другое",
  currency: "KZT",
  price: "",
  qty: "1",
  kind: "Товар",
  description: "",
  visible: true,
});

const SELLER_FIELDS = [
  { name: "name", label: "Название компании", placeholder: "ТОО «Mebel Almaty»", maxLength: 160, required: true, wide: true },
  { name: "bin", label: "БИН / ИИН", placeholder: "12 цифр", maxLength: 14, required: true, inputMode: "numeric" },
  { name: "phone", label: "Телефон", placeholder: SITE.phoneDisplay, maxLength: 40 },
  { name: "address", label: "Адрес", placeholder: "г. Алматы, ул. …", maxLength: 200, wide: true },
  { name: "iban", label: "ИИК (IBAN)", placeholder: "KZ…", maxLength: 24, required: true },
  { name: "bank", label: "Банк", placeholder: "АО «Kaspi Bank»", maxLength: 120, required: true },
  { name: "bik", label: "БИК", placeholder: "CASPKZKA", maxLength: 11, required: true },
  { name: "kbe", label: "Кбе", placeholder: "например, 19", maxLength: 2, required: true, inputMode: "numeric" },
  { name: "knp", label: "Код назначения платежа", placeholder: "например, 710", maxLength: 3, required: true, inputMode: "numeric" },
  { name: "vat_note", label: "Строка про НДС", placeholder: "например, Без НДС", maxLength: 60, required: true },
  { name: "signer", label: "Руководитель (ФИО)", placeholder: "Иванов И. И.", maxLength: 80, wide: true },
];

function SellerSettings() {
  const [seller, setSeller] = useState(null);
  const [complete, setComplete] = useState(false);
  const [errors, setErrors] = useState({});
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api("/api/admin/settings/seller")
      .then((data) => {
        setSeller(data.seller || {});
        setComplete(Boolean(data.complete));
      })
      .catch((err) => setStatus(err.message));
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setStatus("");
    try {
      const response = await fetch("/api/admin/settings/seller", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(seller),
      });
      const data = await response.json().catch(() => null);
      if (!data) {
        setStatus(`Сервер вернул некорректный ответ (HTTP ${response.status})`);
        return;
      }
      if (!response.ok) {
        setErrors(data.fields || {});
        setStatus(data.error || "Не получилось сохранить");
        return;
      }
      setErrors({});
      setSeller(data.seller);
      setComplete(Boolean(data.complete));
      setStatus("Сохранено");
    } catch {
      setStatus("Нет связи с сервером");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="admin-seller">
      <div className="admin-list-head">
        <p className="kicker">Реквизиты для счетов</p>
      </div>
      <div className="admin-crm-panel">
        {!seller ? (
          <p className="shop-status">{status || "Загружаем реквизиты…"}</p>
        ) : (
          <form onSubmit={handleSubmit} noValidate>
            <p className={`admin-seller__state${complete ? " is-ok" : ""}`}>
              {complete
                ? "Реквизиты заполнены — счета выходят без пометки «ОБРАЗЕЦ»."
                : "Пока не заполнены все поля со звёздочкой (включая Кбе, КНП и строку про НДС), счета печатаются с пометкой «ОБРАЗЕЦ»."}
            </p>
            <div className="admin-seller__grid">
              {SELLER_FIELDS.map((field) => (
                <label
                  key={field.name}
                  className={`field${field.wide ? " admin-seller__wide" : ""}${errors[field.name] ? " is-invalid" : ""}`}
                >
                  <span>
                    {field.label}
                    {field.required ? " *" : ""}
                  </span>
                  <input
                    type="text"
                    name={field.name}
                    maxLength={field.maxLength}
                    placeholder={field.placeholder}
                    inputMode={field.inputMode}
                    value={seller[field.name] || ""}
                    onChange={(e) => setSeller((s) => ({ ...s, [field.name]: e.target.value }))}
                  />
                  {errors[field.name] ? <small className="admin-seller__error">{errors[field.name]}</small> : null}
                </label>
              ))}
            </div>
            <div className="admin-seller__actions">
              <button className="btn btn--bronze" type="submit" disabled={saving}>
                {saving ? "Сохраняем…" : "Сохранить реквизиты"}
              </button>
              <p className="form-error" role="status">
                {status}
              </p>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export function AdminPage() {
  const [authed, setAuthed] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [clients, setClients] = useState([]);
  const [chats, setChats] = useState([]);
  const [orderFilter, setOrderFilter] = useState("all");
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [galleryImages, setGalleryImages] = useState([]);
  const [pendingFiles, setPendingFiles] = useState([]);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const fileRef = useRef(null);

  const [deskError, setDeskError] = useState("");
  const [deskBusy, setDeskBusy] = useState(false);
  const [sessionError, setSessionError] = useState("");
  const [health, setHealth] = useState(null);

  useEffect(() => {
    onUnauthorized = () => {
      setAuthed(false);
      setLoginError("Сессия истекла. Войдите снова.");
    };
    return () => {
      onUnauthorized = null;
    };
  }, []);

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await api("/api/admin/health"));
    } catch (err) {
      setHealth({ config_problems: [`состояние сервера не получено: ${err.message}`] });
    }
  }, []);

  const loadDesk = useCallback(async () => {
    setDeskBusy(true);
    const setters = { products: setProducts, orders: setOrders, clients: setClients, chats: setChats };
    const results = await Promise.allSettled(DESK_SOURCES.map(([, url]) => api(url)));
    const failed = [];
    results.forEach((result, index) => {
      const [key, , label] = DESK_SOURCES[index];
      if (result.status === "fulfilled") setters[key](result.value[key] || []);
      else failed.push({ label, message: result.reason?.message || String(result.reason) });
    });
    setDeskBusy(false);
    if (failed.length) {
      const reasons = [...new Set(failed.map((item) => item.message))].join(" ");
      setDeskError(`Не загружены: ${failed.map((item) => item.label).join(", ")}. ${reasons} Показанные данные могут быть неполными.`);
    } else {
      setDeskError("");
    }
    loadHealth();
    return !failed.length;
  }, [loadHealth]);

  const checkSession = useCallback(async () => {
    setSessionError("");
    try {
      const data = await api("/api/session");
      if (!data.ok) return;
      setAuthed(true);
      await loadDesk();
    } catch (err) {
      setSessionError(err.message);
    }
  }, [loadDesk]);

  useEffect(() => {
    document.title = "Кабинет — Mebel Almaty";
    document.body.classList.add("admin");
    checkSession();
    return () => {
      document.body.classList.remove("admin");
      document.body.style.overflow = "";
      document.title = "Mebel Almaty — корпусная мебель на заказ в Алматы";
    };
  }, [checkSession]);

  useEffect(() => {
    const onWheel = (event) => {
      const input = event.target.closest('input[type="number"]');
      if (!input || document.activeElement !== input) return;
      event.preventDefault();
      input.blur();
    };
    document.addEventListener("wheel", onWheel, { passive: false });
    return () => document.removeEventListener("wheel", onWheel);
  }, []);

  const resetForm = () => {
    setForm(emptyForm());
    setGalleryImages([]);
    setPendingFiles([]);
    setFormError("");
  };

  const openForm = (fresh) => {
    if (fresh) resetForm();
    setModalOpen(true);
    document.body.style.overflow = "hidden";
  };

  const closeForm = () => {
    setModalOpen(false);
    document.body.style.overflow = "";
  };

  useEffect(() => {
    if (!modalOpen) return;
    const onKey = (event) => {
      if (event.key === "Escape") closeForm();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [modalOpen]);

  const filteredOrders = useMemo(() => {
    if (orderFilter === "all") return orders;
    return orders.filter((order) => (order.status || "new") === orderFilter);
  }, [orders, orderFilter]);

  const sortedClients = useMemo(() => {
    return [...clients].sort((a, b) => {
      const ha = a.hidden ? 1 : 0;
      const hb = b.hidden ? 1 : 0;
      if (ha !== hb) return ha - hb;
      return String(b.last_order_at || b.updated_at || "").localeCompare(
        String(a.last_order_at || a.updated_at || "")
      );
    });
  }, [clients]);

  const handleLogin = async (event) => {
    event.preventDefault();
    setLoginError("");
    setSessionError("");
    try {
      await api("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          login: event.target.login.value.trim(),
          password: event.target.password.value,
        }),
      });
    } catch (err) {
      setLoginError(err.message);
      return;
    }
    setAuthed(true);
    await loadDesk();
  };

  const handleLogout = async () => {
    closeForm();
    try {
      await api("/api/logout", { method: "POST" });
    } catch (err) {
      setDeskError(`Выйти не удалось: ${err.message}`);
      return;
    }
    setAuthed(false);
  };

  const refreshList = async (url, key, setter) => {
    try {
      const data = await api(url);
      setter(data[key] || []);
      setDeskError((prev) => (prev.startsWith(REFRESH_FAILED) ? "" : prev));
    } catch (err) {
      setDeskError(`${REFRESH_FAILED} ${err.message} Показаны прежние данные.`);
    }
  };

  const handleSaveProduct = async (event) => {
    event.preventDefault();
    setFormError("");
    setSaving(true);
    try {
      const uploaded = [];
      for (const file of pendingFiles) {
        uploaded.push(await uploadPhoto(file));
      }
      const images = [...galleryImages, ...uploaded].slice(0, 8);
      const payload = {
        title: form.title.trim(),
        category: form.category,
        kind: form.kind,
        currency: form.currency,
        qty: form.qty,
        price: form.price,
        description: form.description.trim(),
        visible: form.visible,
        images,
        image: images[0] || "",
      };
      if (form.id) {
        await api(`/api/products/${form.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } else {
        await api("/api/products", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
    } catch (err) {
      setFormError(err.message);
      setSaving(false);
      return;
    }
    setSaving(false);
    resetForm();
    closeForm();
    await refreshList("/api/admin/products", "products", setProducts);
  };

  const editProduct = async (id) => {
    let data;
    try {
      data = await api("/api/admin/products");
    } catch (err) {
      alert(err.message || "Не удалось загрузить товар");
      return;
    }
    const product = (data.products || []).find((item) => item.id === id);
    if (!product) return;
    setForm({
      id: product.id,
      title: product.title || "",
      category: product.category || "Другое",
      currency: product.currency || "KZT",
      price: product.price ?? "",
      qty: product.qty ?? 1,
      kind: product.kind || "Товар",
      description: product.description || "",
      visible: product.visible !== false,
    });
    setGalleryImages(
      Array.isArray(product.images) && product.images.length
        ? product.images.filter(Boolean).slice(0, 8)
        : product.image
          ? [product.image]
          : []
    );
    setPendingFiles([]);
    setFormError("");
    openForm(false);
  };

  const deleteProduct = async (id) => {
    if (!confirm("Убрать этот товар с сайта?")) return;
    try {
      await api(`/api/products/${id}`, { method: "DELETE" });
    } catch (err) {
      alert(err.message || "Не удалось удалить товар");
      return;
    }
    if (form.id === id) {
      resetForm();
      closeForm();
    }
    await refreshList("/api/admin/products", "products", setProducts);
  };

  const pendingPreviews = useMemo(
    () => pendingFiles.map((file) => ({ file, url: URL.createObjectURL(file) })),
    [pendingFiles]
  );

  useEffect(
    () => () => {
      pendingPreviews.forEach((item) => URL.revokeObjectURL(item.url));
    },
    [pendingPreviews]
  );

  return (
    <>
      <header className="admin-top">
        <Link className="brand" to="/">
          <span className="brand__seal">
            <img src="/assets/logo.png" width="120" height="120" alt="" />
          </span>
          <span className="brand__text">
            <span className="brand__name">Mebel Almaty</span>
          </span>
        </Link>
        <div className="admin-side">
          <span className="admin-mark">Админ</span>
          <Link className="btn btn--line" to="/">
            На сайт
          </Link>
        </div>
      </header>

      <main className="admin-main">
        {!authed ? (
          <section className="admin-card" id="login-card">
            <p className="kicker">Вход</p>
            <h1>Добавляйте изделия, они сразу выходят на сайт.</h1>
            <DeskError error={sessionError && `Не удалось проверить вход: ${sessionError}`} onRetry={checkSession} />
            <form id="login-form" onSubmit={handleLogin}>
              <div className="field">
                <label htmlFor="admin-login">Логин</label>
                <input id="admin-login" type="text" name="login" autoComplete="username" required />
              </div>
              <div className="field">
                <label htmlFor="admin-password">Пароль</label>
                <div className="pass">
                  <input
                    id="admin-password"
                    type={showPass ? "text" : "password"}
                    name="password"
                    autoComplete="current-password"
                    required
                  />
                  <button
                    className={`pass__eye${showPass ? " is-on" : ""}`}
                    type="button"
                    aria-label={showPass ? "Скрыть пароль" : "Показать пароль"}
                    aria-pressed={showPass}
                    onClick={() => setShowPass((v) => !v)}
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path className="eye-open" d="M2.5 12S6.2 6.5 12 6.5 21.5 12 21.5 12 17.8 17.5 12 17.5 2.5 12 2.5 12z" fill="none" stroke="currentColor" strokeWidth="1.4" />
                      <circle className="eye-open" cx="12" cy="12" r="2.4" fill="none" stroke="currentColor" strokeWidth="1.4" />
                      <path className="eye-shut" d="M4 5.5l16 13M7 8.2C5 9.4 3.4 11.2 2.5 12c0 0 3.7 5.5 9.5 5.5 1.6 0 3-.3 4.3-.9M10.2 8.1C10.8 7.8 11.4 7.5 12 7.5c5.8 0 9.5 5.5 9.5 5.5-.6.9-1.5 1.9-2.6 2.8" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                    </svg>
                  </button>
                </div>
              </div>
              <p className="form-error" id="login-error" role="alert">
                {loginError}
              </p>
              <button className="btn btn--bronze" type="submit">
                Войти
              </button>
            </form>
          </section>
        ) : (
          <section className={`admin-desk is-open`} id="desk">
            <DeskError error={deskError} onRetry={loadDesk} busy={deskBusy} />
            <HealthBanner health={health} />
            <div className="admin-list-head">
              <p className="kicker">На витрине</p>
              <div className="admin-list-tools">
                <button className="btn btn--bronze" type="button" onClick={() => openForm(true)}>
                  Добавить товар
                </button>
                <button className="btn btn--line" type="button" onClick={handleLogout}>
                  Выйти
                </button>
              </div>
            </div>
            <div className="admin-list" id="list">
              {!products.length ? (
                <p className="shop-status">Пока ничего нет. Добавьте первый товар.</p>
              ) : (
                products.map((product) => (
                  <article className="admin-row" key={product.id}>
                    {product.image ? <img src={product.image} alt="" /> : <span className="admin-row__ph" />}
                    <div>
                      <h2>{product.title}</h2>
                      <p>
                        {product.kind || "Товар"} · {product.qty || 1} шт. · {money(product.price, product.currency)}
                        {!product.visible ? (
                          <>
                            {" · "}
                            <span className="is-hidden">скрыт</span>
                          </>
                        ) : null}
                      </p>
                      <div className="admin-row__tools">
                        <button type="button" onClick={() => editProduct(product.id)}>
                          Изменить
                        </button>
                        <button type="button" onClick={() => deleteProduct(product.id)}>
                          Удалить
                        </button>
                      </div>
                    </div>
                  </article>
                ))
              )}
            </div>

            <div className="admin-orders">
              <div className="admin-list-head">
                <p className="kicker">CRM · Заказы</p>
                <button
                  className="btn btn--line"
                  type="button"
                  onClick={() => refreshList("/api/admin/orders", "orders", setOrders)}
                >
                  Обновить
                </button>
              </div>
              <div className="admin-crm-panel">
                <div className="admin-crm-panel__bar">
                  <h2 className="admin-crm-panel__title">Заказы из WhatsApp</h2>
                  <div className="admin-order-filters" id="order-filters" role="tablist" aria-label="Фильтр заказов">
                    {[
                      ["all", "Все"],
                      ["new", "Новые"],
                      ["in_progress", "В работе"],
                      ["done", "Готово"],
                      ["cancelled", "Отмена"],
                    ].map(([value, label]) => (
                      <button
                        key={value}
                        type="button"
                        className={`admin-filter${orderFilter === value ? " is-on" : ""}`}
                        data-order-filter={value}
                        onClick={() => setOrderFilter(value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="admin-order-list" id="order-list">
                  {!filteredOrders.length ? (
                    <p className="shop-status admin-grid-empty">
                      {orders.length
                        ? "В этом статусе заказов нет."
                        : "Заказов пока нет. Они появятся, когда клиент нажмёт «Заказать» и уйдёт в WhatsApp."}
                    </p>
                  ) : (
                    filteredOrders.map((order) => {
                      const customer = order.customer || {};
                      const who = [customer.name || "???", customer.phone].filter(Boolean).join(" · ");
                      const status = order.status || "new";
                      const items = order.items || [];
                      const totals = orderTotals(items);
                      const wa = clientWaLink(order);
                      const fullMessage = String(order.message || order.wa_text || "").trim();
                      const showMessage = items.length && fullMessage && fullMessage.length > 20;
                      return (
                        <article className="admin-order" data-order-id={order.id} key={order.id}>
                          <div className="admin-order__top">
                            <span className="admin-order__code">
                              #{orderShortId(order.id)} · {SOURCE_LABEL[order.source] || order.source || "сайт"}
                            </span>
                            <span className={`admin-order__badge ${STATUS_CLASS[status] || ""}`}>
                              {STATUS_LABEL[status] || status}
                            </span>
                          </div>
                          <p className="admin-order__who">{who}</p>
                          <p className="admin-order__when">{formatChatTime(order.created_at)}</p>
                          <ul className="admin-order__items">
                            {order.items_corrupted ? (
                              <li className="admin-order__corrupt" role="alert">
                                <span>Позиции заказа повреждены в базе — счёт не сформируется. Сверьтесь с WhatsApp-перепиской.</span>
                                <em />
                              </li>
                            ) : null}
                            {items.length ? (
                              items.map((item, i) => {
                                const qty = Number(item.qty) || 1;
                                const right =
                                  item.price != null && item.price !== ""
                                    ? `${qty} × ${money(item.price, item.currency)}`
                                    : `${qty} шт.`;
                                return (
                                  <li key={i}>
                                    <span>{item.title || "Позиция"}</span>
                                    <em>{right}</em>
                                  </li>
                                );
                              })
                            ) : (
                              <li>
                                <span>{(order.message || order.wa_text || "Заявка без позиций").slice(0, 220)}</span>
                                <em />
                              </li>
                            )}
                          </ul>
                          {showMessage ? <p className="admin-order__note">{fullMessage.slice(0, 280)}</p> : null}
                          {totals.length ? (
                            <p className="admin-order__total">{totals.join(" · ")}</p>
                          ) : (
                            <p className="admin-order__total admin-order__total--muted">цена по запросу</p>
                          )}
                          <div className="admin-order__actions">
                            <label className="admin-order__status">
                              <span className="visually-hidden">Статус</span>
                              <select
                                data-status
                                value={status}
                                onChange={async (e) => {
                                  try {
                                    const data = await api(`/api/orders/${order.id}`, {
                                      method: "PATCH",
                                      headers: { "Content-Type": "application/json" },
                                      body: JSON.stringify({ status: e.target.value }),
                                    });
                                    setOrders((prev) => prev.map((item) => (item.id === data.order.id ? data.order : item)));
                                  } catch (err) {
                                    alert(err.message || "Не удалось обновить статус");
                                  }
                                }}
                              >
                                {Object.entries(STATUS_LABEL).map(([value, label]) => (
                                  <option key={value} value={value}>
                                    {label}
                                  </option>
                                ))}
                              </select>
                            </label>
                            {wa ? (
                              <a className="btn btn--bronze" href={wa} target="_blank" rel="noopener noreferrer">
                                WhatsApp
                              </a>
                            ) : (
                              <span className="admin-order__hint">Нет телефона</span>
                            )}
                            <a
                              className="btn btn--line"
                              href={`/api/orders/${encodeURIComponent(order.id)}/pdf`}
                              target="_blank"
                              rel="noopener"
                            >
                              🧾 Счёт (PDF)
                            </a>
                            <button
                              className="btn btn--ghost-danger"
                              type="button"
                              onClick={async () => {
                                if (!window.confirm("Удалить этот заказ?")) return;
                                try {
                                  await api(`/api/orders/${order.id}`, { method: "DELETE" });
                                  setOrders((prev) => prev.filter((item) => item.id !== order.id));
                                } catch (err) {
                                  alert(err.message || "Не удалось удалить");
                                  return;
                                }
                                await refreshList("/api/admin/clients", "clients", setClients);
                              }}
                            >
                              Удалить
                            </button>
                          </div>
                        </article>
                      );
                    })
                  )}
                </div>
              </div>
            </div>

            <div className="admin-clients">
              <div className="admin-list-head">
                <p className="kicker">CRM · Клиенты</p>
                <button
                  className="btn btn--line"
                  type="button"
                  onClick={() => refreshList("/api/admin/clients", "clients", setClients)}
                >
                  Обновить
                </button>
              </div>
              <div className="admin-crm-panel">
                <h2 className="admin-crm-panel__title">Клиенты</h2>
                <div className="admin-client-list" id="client-list">
                  {!sortedClients.length ? (
                    <p className="shop-status admin-grid-empty">
                      Клиентов пока нет. Они сохраняются автоматически из заявок без дублей по телефону.
                    </p>
                  ) : (
                    sortedClients.map((client) => {
                      const wa = clientCardWaLink(client);
                      const count = Number(client.orders_count) || 0;
                      const hidden = Boolean(client.hidden);
                      return (
                        <article className={`admin-client${hidden ? " is-hidden" : ""}`} data-client-id={client.id} key={client.id}>
                          <div className="admin-client__top">
                            <div className="admin-client__who">
                              <strong>{client.name || "Клиент"}</strong>
                              <span className="admin-client__phone">{client.phone || "без телефона"}</span>
                            </div>
                            <span className="admin-client__badge">{hidden ? "скрыт" : `${count} зак.`}</span>
                          </div>
                          <p className="admin-client__meta">
                            {hidden ? "Скрыт из активного списка" : clientMetaLine(client)}
                          </p>
                          <label className="admin-client__note">
                            <span>Заметка</span>
                            <textarea
                              data-client-note
                              rows={3}
                              maxLength={1000}
                              placeholder="Комментарий по клиенту"
                              defaultValue={client.note || ""}
                              key={`${client.id}-${client.note || ""}`}
                            />
                          </label>
                          <div className="admin-client__actions">
                            <button
                              className="btn btn--line"
                              type="button"
                              onClick={async (e) => {
                                const card = e.currentTarget.closest("[data-client-id]");
                                const note = card?.querySelector("[data-client-note]")?.value || "";
                                const btn = e.currentTarget;
                                btn.disabled = true;
                                try {
                                  await api(`/api/clients/${client.id}`, {
                                    method: "PATCH",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({ note }),
                                  });
                                  btn.textContent = "Сохранено";
                                  window.setTimeout(() => {
                                    btn.textContent = "Сохранить";
                                  }, 1200);
                                } catch (err) {
                                  alert(err.message || "Не удалось сохранить");
                                } finally {
                                  btn.disabled = false;
                                }
                              }}
                            >
                              Сохранить
                            </button>
                            {wa ? (
                              <a className="btn btn--bronze" href={wa} target="_blank" rel="noopener noreferrer">
                                WhatsApp
                              </a>
                            ) : (
                              <span className="admin-order__hint">Нет телефона</span>
                            )}
                            {hidden ? (
                              <button
                                className="btn btn--line"
                                type="button"
                                onClick={async () => {
                                  try {
                                    await api(`/api/clients/${client.id}`, {
                                      method: "PATCH",
                                      headers: { "Content-Type": "application/json" },
                                      body: JSON.stringify({ hidden: false }),
                                    });
                                  } catch (err) {
                                    alert(err.message || "Не удалось сохранить");
                                    return;
                                  }
                                  await refreshList("/api/admin/clients", "clients", setClients);
                                }}
                              >
                                Вернуть
                              </button>
                            ) : (
                              <button
                                className="btn btn--ghost-danger"
                                type="button"
                                onClick={async () => {
                                  try {
                                    await api(`/api/clients/${client.id}`, {
                                      method: "PATCH",
                                      headers: { "Content-Type": "application/json" },
                                      body: JSON.stringify({ hidden: true }),
                                    });
                                  } catch (err) {
                                    alert(err.message || "Не удалось сохранить");
                                    return;
                                  }
                                  await refreshList("/api/admin/clients", "clients", setClients);
                                }}
                              >
                                Скрыть
                              </button>
                            )}
                          </div>
                        </article>
                      );
                    })
                  )}
                </div>
              </div>
            </div>

            <div className="admin-chats">
              <div className="admin-list-head">
                <p className="kicker">Диалоги чата</p>
                <button
                  className="btn btn--line"
                  type="button"
                  onClick={() => refreshList("/api/admin/chats", "chats", setChats)}
                >
                  Обновить
                </button>
              </div>
              <div className="admin-chat-list" id="chat-list">
                {!chats.length ? (
                  <p className="shop-status">Пока нет диалогов. Они появятся, когда гости напишут в чат на сайте.</p>
                ) : (
                  chats.map((chat) => {
                    const count = (chat.messages || []).length;
                    return (
                      <details className="admin-chat" key={chat.id || chat.preview}>
                        <summary>
                          <strong>{chat.preview || "Диалог"}</strong>
                          <span>
                            {formatChatTime(chat.updated_at)} · {count} сообщ.
                          </span>
                        </summary>
                        <div className="admin-chat-thread">
                          {(chat.messages || []).map((msg, i) => (
                            <div className={`admin-chat-msg admin-chat-msg--${msg.role || "user"}`} key={i}>
                              <span>
                                {msg.role === "assistant" ? "Консультант" : "Клиент"} · {formatChatTime(msg.at)}
                              </span>
                              <p>{msg.content || ""}</p>
                            </div>
                          ))}
                        </div>
                      </details>
                    );
                  })
                )}
              </div>
            </div>

            <SellerSettings />
          </section>
        )}
      </main>

      {modalOpen ? (
        <div
          className="modal"
          id="product-modal"
          onClick={(event) => {
            if (event.target === event.currentTarget) closeForm();
          }}
        >
          <div className="modal__panel" role="dialog" aria-modal="true" aria-labelledby="form-title">
            <div className="modal__head">
              <h2 id="form-title">{form.id ? "Изменить товар" : "Новый товар"}</h2>
              <button className="modal__close" type="button" onClick={closeForm} aria-label="Закрыть">
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M3.5 3.5 12.5 12.5M12.5 3.5 3.5 12.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                </svg>
              </button>
            </div>
            <form id="product-form" onSubmit={handleSaveProduct}>
              <input type="hidden" name="id" value={form.id} readOnly />
              <label className="field">
                <span>Название</span>
                <input
                  type="text"
                  name="title"
                  required
                  maxLength={120}
                  placeholder="Шкаф в нишу, шпон дуба"
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                />
              </label>
              <div className="form-pair">
                <div className="field">
                  <span id="category-label">Раздел</span>
                  <Pick
                    name="category"
                    labelId="category-label"
                    value={form.category}
                    onChange={(v) => setForm((f) => ({ ...f, category: v }))}
                    options={CATEGORIES.map((c) => ({ value: c, label: c }))}
                  />
                </div>
                <div className="field">
                  <span id="currency-label">Валюта</span>
                  <Pick
                    name="currency"
                    labelId="currency-label"
                    value={form.currency}
                    onChange={(v) => setForm((f) => ({ ...f, currency: v }))}
                    options={CURRENCIES}
                  />
                </div>
              </div>
              <div className="form-pair">
                <label className="field">
                  <span>Цена</span>
                  <input
                    type="number"
                    name="price"
                    min="0"
                    step="1"
                    placeholder="185000"
                    value={form.price}
                    onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))}
                  />
                </label>
                <label className="field">
                  <span>Количество</span>
                  <input
                    type="number"
                    name="qty"
                    min="1"
                    step="1"
                    value={form.qty}
                    onChange={(e) => setForm((f) => ({ ...f, qty: e.target.value }))}
                  />
                </label>
              </div>
              <div className="field">
                <span id="kind-label">Тип</span>
                <Pick
                  name="kind"
                  labelId="kind-label"
                  value={form.kind}
                  onChange={(v) => setForm((f) => ({ ...f, kind: v }))}
                  options={KINDS.map((k) => ({ value: k, label: k }))}
                />
              </div>
              <label className="field">
                <span>Описание</span>
                <textarea
                  name="description"
                  rows={5}
                  maxLength={500}
                  placeholder="Ширина 2,4 м, матовые фасады, доводчики."
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                />
              </label>
              <div className="field">
                <span>Фото (до 8 ракурсов)</span>
                <div className="file">
                  <input
                    className="file__native"
                    type="file"
                    name="photo"
                    accept="image/jpeg,image/png,image/webp"
                    multiple
                    ref={fileRef}
                    onChange={(e) => {
                      const files = [...e.target.files];
                      e.target.value = "";
                      const room = Math.max(0, 8 - galleryImages.length - pendingFiles.length);
                      setPendingFiles((prev) => [...prev, ...files.slice(0, room)]);
                    }}
                  />
                  <button className="file__btn" type="button" onClick={() => fileRef.current?.click()}>
                    <span className="file__label">Добавить фото</span>
                    <span className={`file__name${pendingFiles.length ? " is-set" : ""}`}>
                      {pendingFiles.length
                        ? pendingFiles.length === 1
                          ? pendingFiles[0].name
                          : `выбрано ${pendingFiles.length}`
                        : "не выбрано"}
                    </span>
                  </button>
                </div>
                {galleryImages.length || pendingPreviews.length ? (
                  <div className="admin-gallery" id="admin-gallery">
                    {galleryImages.map((src, index) => (
                      <div className="admin-gallery__item" key={`s-${src}`}>
                        <img src={src} alt="" />
                        <button
                          type="button"
                          aria-label="Убрать фото"
                          onClick={() => setGalleryImages((prev) => prev.filter((_, i) => i !== index))}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                    {pendingPreviews.map((item, index) => (
                      <div className="admin-gallery__item" key={`p-${item.file.name}-${index}`}>
                        <img src={item.url} alt="" />
                        <button
                          type="button"
                          aria-label="Убрать фото"
                          onClick={() => setPendingFiles((prev) => prev.filter((_, i) => i !== index))}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
              <img className="admin-preview" id="preview" alt="" hidden />
              <label className="admin-check">
                <input
                  type="checkbox"
                  name="visible"
                  checked={form.visible}
                  onChange={(e) => setForm((f) => ({ ...f, visible: e.target.checked }))}
                />
                Показывать на сайте
              </label>
              <p className="form-error" id="form-error" role="status">
                {formError}
              </p>
              <div className="admin-actions">
                <button className="btn btn--bronze" type="submit" id="save-button" disabled={saving}>
                  {form.id ? "Сохранить" : "Выложить на сайт"}
                </button>
                {form.id ? (
                  <button
                    className="btn btn--line"
                    type="button"
                    id="reset-button"
                    onClick={() => {
                      resetForm();
                      closeForm();
                    }}
                  >
                    Отменить правку
                  </button>
                ) : null}
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </>
  );
}
