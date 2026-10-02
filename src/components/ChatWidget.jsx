import { useCallback, useEffect, useRef, useState } from "react";
import { SITE } from "../site";
import { useCrm } from "../context/CrmContext";

const CHAT_KEY = "mebel-chat-id";
const WIDTH_KEY = "mebel-chat-width";
const MAX_FILES = 3;
const MAX_BYTES = 4 * 1024 * 1024;
// Фото сжимаются в браузере до 1280px, поэтому исходник может быть больше лимита сервера.
const MAX_IMAGE_SOURCE_BYTES = 25 * 1024 * 1024;
const REQUEST_TIMEOUT_MS = 70000;
const OFFLINE_TEXT = "Нет связи с сервером. Проверьте интернет или напишите мастеру в WhatsApp.";
const TIMEOUT_TEXT = "ИИ-консультант не ответил за 70 секунд. Попробуйте ещё раз или напишите мастеру в WhatsApp.";
const MIN_WIDTH = 280;

class ChatError extends Error {
  constructor(message, { status = 0, waText = "", aiDown = false } = {}) {
    super(message);
    this.name = "ChatError";
    this.status = status;
    this.waText = waText;
    this.aiDown = aiDown;
  }
}

const chips = [
  "Рассчитать стоимость",
  "Готовые изделия",
  "Выезд замерщика",
  "Связаться с мастером",
];

let msgSeq = 0;
const nextId = (prefix) => `${prefix}${Date.now()}-${++msgSeq}`;

// Хранилище может быть недоступно (приватный режим, запрет cookie во встроенном браузере).
function storageGet(storage, key) {
  try {
    return window[storage].getItem(key);
  } catch {
    return null;
  }
}

function storageSet(storage, key, value) {
  try {
    window[storage].setItem(key, value);
  } catch {
    /* ignore */
  }
}

let memoryChatId = "";

function getChatId() {
  let id = storageGet("sessionStorage", CHAT_KEY) || memoryChatId;
  if (!id) {
    // По id сервер подставляет историю диалога — он должен быть неподбираемым.
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    id = `c${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
    storageSet("sessionStorage", CHAT_KEY, id);
  }
  memoryChatId = id;
  return id;
}

const base64Bytes = (data) => Math.floor((String(data || "").length * 3) / 4);

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const comma = result.indexOf(",");
      const data = comma >= 0 ? result.slice(comma + 1) : result;
      if (!data) {
        reject(new Error("Не удалось прочитать файл"));
        return;
      }
      resolve({ dataUrl: result, data });
    };
    reader.onerror = () => reject(new Error("Не удалось прочитать файл"));
    reader.readAsDataURL(file);
  });
}

function readFilePayload(file) {
  return new Promise((resolve, reject) => {
    const name = file.name || "file";
    const ext = name.includes(".") ? `.${name.split(".").pop().toLowerCase()}` : "";
    const imageExt = [".jpg", ".jpeg", ".png", ".webp", ".gif"];
    const isImage = (file.type || "").startsWith("image/") || imageExt.includes(ext);

    const finishRaw = async () => {
      try {
        const { data } = await fileToBase64(file);
        resolve({
          name,
          type: file.type || "application/octet-stream",
          data,
          preview: "",
        });
      } catch (err) {
        reject(err);
      }
    };

    if (!isImage) {
      finishRaw();
      return;
    }

    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => {
      try {
        const max = 1280;
        const scale = Math.min(1, max / Math.max(image.width || 1, image.height || 1));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round((image.width || 1) * scale));
        canvas.height = Math.max(1, Math.round((image.height || 1) * scale));
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          URL.revokeObjectURL(url);
          finishRaw();
          return;
        }
        ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        const dataUrl = canvas.toDataURL("image/jpeg", 0.84);
        const comma = dataUrl.indexOf(",");
        const data = comma >= 0 ? dataUrl.slice(comma + 1) : "";
        if (!data) {
          finishRaw();
          return;
        }
        resolve({
          name,
          type: "image/jpeg",
          data,
          preview: dataUrl,
        });
      } catch {
        URL.revokeObjectURL(url);
        finishRaw();
      }
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      finishRaw();
    };
    image.src = url;
  });
}

export function ChatWidget() {
  const { openWhatsApp } = useCrm();
  const rootRef = useRef(null);
  const threadRef = useRef(null);
  const inputRef = useRef(null);
  const fileRef = useRef(null);
  const imageRef = useRef(null);
  const pickingRef = useRef(false);
  const historyRef = useRef([]);

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      role: "bot",
      text: "Здравствуйте! Я ИИ-консультант Mebel Almaty. Напишите вопрос или нажмите «+», чтобы отправить фото или файл — при необходимости переведу вас к мастеру в WhatsApp.",
    },
  ]);
  const [pending, setPending] = useState([]);
  const pendingRef = useRef([]);
  const [sending, setSending] = useState(false);
  const sendingRef = useRef(false);
  const [text, setText] = useState("");
  const [resizing, setResizing] = useState(false);
  const [attachMenu, setAttachMenu] = useState(false);
  const [aiDown, setAiDown] = useState(false);
  const plusWrapRef = useRef(null);

  useEffect(() => {
    pendingRef.current = pending;
  }, [pending]);

  const maxWidth = () => Math.min(560, window.innerWidth - 32);

  const applyWidth = useCallback((value) => {
    const root = rootRef.current;
    if (!root) return 340;
    const width = Math.max(MIN_WIDTH, Math.min(maxWidth(), Number(value) || 340));
    root.style.setProperty("--chat-width", `${width}px`);
    return width;
  }, []);

  useEffect(() => {
    applyWidth(storageGet("localStorage", WIDTH_KEY) || 340);
    const onResize = () => {
      applyWidth(parseInt(getComputedStyle(rootRef.current).getPropertyValue("--chat-width"), 10) || 340);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [applyWidth]);

  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [messages, open]);

  // Не прокручивать страницу под открытым чатом (как в старом chat.js).
  useEffect(() => {
    const root = rootRef.current;
    if (!root || !open) return undefined;

    const onWheel = (event) => {
      const thread = threadRef.current;
      const onThread = thread && thread.contains(event.target);
      if (onThread && thread.scrollHeight > thread.clientHeight + 1) {
        const atTop = thread.scrollTop <= 0 && event.deltaY < 0;
        const atBottom =
          thread.scrollTop + thread.clientHeight >= thread.scrollHeight - 1 && event.deltaY > 0;
        if (!atTop && !atBottom) return;
      }
      event.preventDefault();
    };

    const onTouchMove = (event) => {
      const thread = threadRef.current;
      if (thread && thread.contains(event.target)) return;
      event.preventDefault();
    };

    root.addEventListener("wheel", onWheel, { passive: false });
    root.addEventListener("touchmove", onTouchMove, { passive: false });
    return () => {
      root.removeEventListener("wheel", onWheel);
      root.removeEventListener("touchmove", onTouchMove);
    };
  }, [open]);

  useEffect(() => {
    if (!open) setAttachMenu(false);
  }, [open]);

  useEffect(() => {
    const onKey = (event) => {
      if (event.key !== "Escape") return;
      if (document.body.classList.contains("is-lead-open")) return;
      if (attachMenu) {
        setAttachMenu(false);
        return;
      }
      if (open) setOpen(false);
    };
    const onDocClick = (event) => {
      if (pickingRef.current || !open || !rootRef.current) return;
      // Форма заявки открывается из чата поверх страницы — клик по ней не должен закрывать чат.
      if (event.target instanceof Element && event.target.closest(".lead-modal")) return;
      if (attachMenu && plusWrapRef.current?.contains(event.target)) return;
      if (attachMenu) setAttachMenu(false);
      if (rootRef.current.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("click", onDocClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("click", onDocClick);
    };
  }, [open, attachMenu]);

  const openPicker = (kind = "file") => {
    setAttachMenu(false);
    pickingRef.current = true;
    const target = kind === "image" ? imageRef.current : fileRef.current;
    target?.click();
    window.setTimeout(() => {
      pickingRef.current = false;
    }, 1200);
  };

  const wa = (msg) => `https://wa.me/${SITE.phoneE164}?text=${encodeURIComponent(msg)}`;

  const fallbackWaText = (latest) => {
    const notes = historyRef.current
      .filter((item) => item.role === "user")
      .map((item) => item.content)
      .slice(-6);
    if (latest && notes[notes.length - 1] !== latest) notes.push(latest);
    const brief = notes.length ? notes.join(" · ") : "Клиент просит связаться с мастером.";
    return `Здравствуйте! Меня направил ИИ-консультант с сайта Mebel Almaty.\n\nЗапрос клиента:\n${brief}\n\nПрошу связаться и продолжить консультацию.`;
  };

  const startResize = (event) => {
    event.preventDefault();
    event.stopPropagation();
    const panel = rootRef.current?.querySelector(".chat__panel");
    if (!panel) return;
    const startX = event.clientX ?? event.touches?.[0]?.clientX;
    const startWidth = panel.getBoundingClientRect().width;
    if (startX == null) return;
    setResizing(true);

    const move = (moveEvent) => {
      const clientX = moveEvent.clientX ?? moveEvent.touches?.[0]?.clientX;
      if (clientX == null) return;
      applyWidth(startWidth + (startX - clientX));
    };

    const stop = () => {
      setResizing(false);
      storageSet(
        "localStorage",
        WIDTH_KEY,
        String(parseInt(getComputedStyle(rootRef.current).getPropertyValue("--chat-width"), 10) || 340)
      );
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", stop);
      document.removeEventListener("touchmove", move);
      document.removeEventListener("touchend", stop);
    };

    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", stop);
    document.addEventListener("touchmove", move, { passive: false });
    document.addEventListener("touchend", stop);
  };

  const ask = async (raw) => {
    const message = String(raw || "").trim();
    if (sendingRef.current) return;
    const files = [...pendingRef.current].filter((item) => item?.data);
    if (!message && !files.length) {
      if (pendingRef.current.length) {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId("w"),
            role: "bot",
            text: "Файл ещё не готов к отправке. Нажмите «+» и выберите его ещё раз.",
          },
        ]);
      }
      return;
    }

    const historyText = files.length
      ? `${message}${message ? "\n" : ""}[вложения: ${files.map((item) => item.name).join(", ")}]`
      : message;

    const snapshotPending = [...pendingRef.current];
    pendingRef.current = [];
    setPending([]);

    sendingRef.current = true;
    setSending(true);
    setMessages((prev) => [
      ...prev,
      {
        id: nextId("u"),
        role: "user",
        text: message,
        files: files.map((item) => ({ name: item.name, preview: item.preview })),
      },
      { id: nextId("t"), role: "bot", typing: true },
    ]);
    const userTurn = { role: "user", content: historyText || "Вложение" };
    historyRef.current.push(userTurn);
    setText("");

    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      let response;
      try {
        response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.signal,
          body: JSON.stringify({
            message,
            chat_id: getChatId(),
            attachments: files.map((item) => ({
              name: item.name,
              type: item.type || "application/octet-stream",
              data: item.data,
            })),
          }),
        });
      } catch (err) {
        throw new ChatError(err?.name === "AbortError" ? TIMEOUT_TEXT : OFFLINE_TEXT);
      }
      const data = await response.json().catch(() => null);
      if (!data) {
        throw new ChatError(`Сервер вернул некорректный ответ (ошибка ${response.status}). Напишите мастеру в WhatsApp.`, {
          status: response.status,
        });
      }
      if (!response.ok) {
        const aiDown = data.code === "ai_unavailable" || data.code === "ai_not_configured";
        const reason = typeof data.error === "string" && data.error ? data.error : "Не удалось получить ответ.";
        throw new ChatError(`${reason} (ошибка ${response.status})`, {
          status: response.status,
          waText: data.wa_text,
          aiDown,
        });
      }
      if (typeof data.reply !== "string" || !data.reply.trim()) {
        throw new ChatError("ИИ-консультант прислал пустой ответ. Напишите мастеру в WhatsApp.", { status: response.status });
      }
      setAiDown(false);
      if (data.chat_id) {
        memoryChatId = data.chat_id;
        storageSet("sessionStorage", CHAT_KEY, data.chat_id);
      }
      const reply = data.reply;
      historyRef.current.push({ role: "assistant", content: reply });
      setMessages((prev) => [
        ...prev.filter((m) => !m.typing),
        {
          id: nextId("b"),
          role: "bot",
          text: reply,
          whatsapp: Boolean(data.whatsapp),
          context: historyText,
          waText: data.wa_text,
          cta: data.cta || "Связаться с мастером",
        },
        ...(data.attachment_warning
          ? [{ id: nextId("w"), role: "bot", error: true, text: data.attachment_warning }]
          : []),
      ]);
    } catch (err) {
      if (err instanceof ChatError && err.aiDown) setAiDown(true);
      // Неотвеченный вопрос убираем из истории и возвращаем в поле — его можно отправить повторно.
      const at = historyRef.current.lastIndexOf(userTurn);
      if (at >= 0) historyRef.current.splice(at, 1);
      setText((current) => current || message);
      pendingRef.current = snapshotPending;
      setPending(snapshotPending);
      setMessages((prev) => [
        ...prev.filter((m) => !m.typing),
        {
          id: nextId("e"),
          role: "bot",
          error: true,
          text: err.message || OFFLINE_TEXT,
          whatsapp: true,
          context: historyText,
          waText: err.waText || "",
          cta: "Написать мастеру",
        },
      ]);
    } finally {
      window.clearTimeout(timer);
      sendingRef.current = false;
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const onFiles = async (fileList) => {
    pickingRef.current = false;
    const files = [...fileList];
    const next = [...pendingRef.current];
    const tooBig = (name) =>
      setMessages((prev) => [
        ...prev,
        { id: nextId("w"), role: "bot", text: `Файл «${name}» слишком большой. Максимум 4 МБ.` },
      ]);
    for (const file of files) {
      if (next.length >= MAX_FILES) {
        setMessages((prev) => [
          ...prev,
          { id: nextId("w"), role: "bot", text: "Можно прикрепить не больше 3 файлов за одно сообщение." },
        ]);
        break;
      }
      const isImage = (file.type || "").startsWith("image/");
      if (file.size > (isImage ? MAX_IMAGE_SOURCE_BYTES : MAX_BYTES)) {
        tooBig(file.name);
        continue;
      }
      try {
        const payload = await readFilePayload(file);
        if (!payload?.data) {
          setMessages((prev) => [
            ...prev,
            { id: nextId("w"), role: "bot", text: `Файл «${file.name}» не удалось прочитать.` },
          ]);
          continue;
        }
        if (base64Bytes(payload.data) > MAX_BYTES) {
          tooBig(file.name);
          continue;
        }
        next.push(payload);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          { id: nextId("w"), role: "bot", text: err.message || "Файл не удалось прикрепить." },
        ]);
      }
    }
    pendingRef.current = next;
    setPending(next);
    inputRef.current?.focus();
  };

  return (
    <div className={`chat${open ? " is-open" : ""}${resizing ? " is-resizing" : ""}`} ref={rootRef}>
      <div className="chat__panel" id="chat-panel" hidden={!open}>
        <button className="chat__resize" type="button" aria-label="Изменить ширину чата" onPointerDown={startResize} onTouchStart={startResize} />
        <div className="chat__head">
          <span className="chat__seal">
            <img src="/assets/logo.png" width="40" height="40" alt="" />
          </span>
          <div>
            <p className="chat__name">ИИ-консультант</p>
            <p className={`chat__status${aiDown ? " is-down" : ""}`}>
              {aiDown ? "Mebel Almaty · ИИ временно недоступен" : "Mebel Almaty · онлайн"}
            </p>
          </div>
          <button className="chat__x" type="button" aria-label="Закрыть чат" onClick={() => setOpen(false)}>
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3.5 3.5 12.5 12.5M12.5 3.5 3.5 12.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <div className="chat__thread" id="chat-thread" ref={threadRef}>
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`chat__msg chat__msg--${msg.role}${msg.typing ? " chat__typing" : ""}${msg.error ? " chat__msg--error" : ""}`}
              role={msg.error ? "alert" : undefined}
            >
              {msg.typing ? (
                <p className="chat__bubble">
                  <span /><span /><span />
                </p>
              ) : (
                <>
                  {msg.files?.length ? (
                    <div className="chat__msg-files">
                      {msg.files.map((file, i) =>
                        file.preview ? (
                          <img key={`${file.name}-${i}`} className="chat__thumb" src={file.preview} alt={file.name || "фото"} />
                        ) : (
                          <span key={`${file.name}-${i}`} className="chat__file-chip">{file.name || "файл"}</span>
                        )
                      )}
                    </div>
                  ) : null}
                  {msg.text ? (
                    <p className="chat__bubble">
                      {msg.text.split("\n").map((line, i) => (
                        <span key={i}>
                          {i > 0 ? <br /> : null}
                          {line}
                        </span>
                      ))}
                    </p>
                  ) : null}
                  {msg.whatsapp ? (
                    <a
                      className="chat__wa"
                      href={wa(msg.waText || fallbackWaText(msg.context || msg.text))}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(event) => {
                        event.preventDefault();
                        const waMsg = msg.waText || fallbackWaText(msg.context || msg.text);
                        openWhatsApp(wa(waMsg), {
                          source: "chat",
                          message: waMsg,
                          items: [{ title: "Консультация в чате", qty: 1, kind: "Заявка" }],
                        });
                      }}
                    >
                      {msg.cta || "Связаться с мастером"}
                    </a>
                  ) : null}
                </>
              )}
            </div>
          ))}
        </div>
        <div className="chat__chips">
          {chips.map((chip) => (
            <button key={chip} type="button" data-chat-chip onClick={() => ask(chip)}>
              {chip}
            </button>
          ))}
        </div>
        {pending.length ? (
          <div className="chat__attach-list" id="chat-attach-list">
            {pending.map((item, index) => (
              <span className="chat__pending" key={`${item.name}-${index}`}>
                {item.preview ? <img src={item.preview} alt="" /> : <span className="chat__pending-ico" aria-hidden="true" />}
                <em>{item.name}</em>
                <button
                  type="button"
                  aria-label={`Убрать ${item.name}`}
                  onClick={() => {
                    const next = pendingRef.current.filter((_, i) => i !== index);
                    pendingRef.current = next;
                    setPending(next);
                  }}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : null}
        <form
          className="chat__form"
          id="chat-form"
          onSubmit={(e) => {
            e.preventDefault();
            ask(text);
          }}
        >
          <input
            className="chat__file"
            id="chat-file"
            type="file"
            accept="*/*"
            multiple
            hidden
            ref={fileRef}
            onChange={(e) => {
              onFiles(e.target.files || []);
              e.target.value = "";
            }}
          />
          <input
            className="chat__file"
            id="chat-image"
            type="file"
            accept="image/*"
            multiple
            hidden
            ref={imageRef}
            onChange={(e) => {
              onFiles(e.target.files || []);
              e.target.value = "";
            }}
          />
          <div className="chat__composer">
            <div className="chat__plus-wrap" ref={plusWrapRef}>
              <button
                className={`chat__attach${pending.length ? " has-files" : ""}${attachMenu ? " is-open" : ""}`}
                type="button"
                id="chat-plus"
                title="Добавить"
                aria-label="Добавить вложение"
                aria-expanded={attachMenu}
                aria-haspopup="menu"
                aria-controls="chat-plus-menu"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setAttachMenu((prev) => !prev);
                }}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M12 5v14M5 12h14"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                  />
                </svg>
                {pending.length ? (
                  <span className="chat__attach-badge" id="chat-attach-badge">
                    {pending.length}
                  </span>
                ) : null}
              </button>
              {attachMenu ? (
                <div className="chat__plus-menu" id="chat-plus-menu" role="menu">
                  <button
                    type="button"
                    role="menuitem"
                    className="chat__plus-item"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      openPicker("image");
                    }}
                  >
                    <span className="chat__plus-ico chat__plus-ico--photo" aria-hidden="true">
                      <svg viewBox="0 0 24 24">
                        <rect
                          x="4"
                          y="6"
                          width="16"
                          height="13"
                          rx="2"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.45"
                        />
                        <circle cx="12" cy="12.5" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.45" />
                        <path
                          d="M8 6.2 9.2 4.5h5.6L16 6.2"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.45"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </span>
                    <span className="chat__plus-copy">
                      <strong>Отправить фото</strong>
                      <em>JPG, PNG, WebP · ИИ увидит</em>
                    </span>
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="chat__plus-item"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      openPicker("file");
                    }}
                  >
                    <span className="chat__plus-ico" aria-hidden="true">
                      <svg viewBox="0 0 24 24">
                        <path
                          d="M14 3H7.5A2.5 2.5 0 0 0 5 5.5v13A2.5 2.5 0 0 0 7.5 21h9a2.5 2.5 0 0 0 2.5-2.5V9l-5-6z"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.45"
                          strokeLinejoin="round"
                        />
                        <path
                          d="M14 3v5.5h5"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.45"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </span>
                    <span className="chat__plus-copy">
                      <strong>Отправить файл</strong>
                      <em>PDF, Word, Excel и др. · до 4 МБ</em>
                    </span>
                  </button>
                </div>
              ) : null}
            </div>
            <label className="visually-hidden" htmlFor="chat-text">
              Сообщение
            </label>
            <textarea
              id="chat-text"
              name="message"
              rows={1}
              maxLength={500}
              placeholder="Напишите, прикрепите фото или файл…"
              ref={inputRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  ask(text);
                }
              }}
            />
          </div>
          <button className="chat__send" type="submit" id="chat-send" title="Отправить" aria-label="Отправить" disabled={sending}>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M4.2 12.1 19.5 4.8l-4.2 14.4-3.4-5.2-5.2-3.4z"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </form>
      </div>
      <button
        className="chat__toggle"
        type="button"
        aria-expanded={open}
        aria-controls="chat-panel"
        aria-label={open ? "Закрыть чат" : "Открыть чат"}
        hidden={open}
        onClick={() => setOpen(true)}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v7A2.5 2.5 0 0 1 16.5 16H9l-4 3.2V6.5z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  );
}
