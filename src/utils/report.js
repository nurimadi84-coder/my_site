const MAX_REPORTS = 10;
let sent = 0;

/** Отправить ошибку фронтенда на сервер (logs/error.log). Сама никогда не бросает исключений. */
export function reportError(kind, error, extra = {}) {
  console.error(`[${kind}]`, error);
  if (sent >= MAX_REPORTS) return;
  sent += 1;
  const err = error instanceof Error ? error : new Error(String(error?.message || error || "unknown"));
  // Сервер принимает до 8 КБ: длинный стек обрезаем, иначе отчёт отклонят целиком.
  const body = JSON.stringify({
    kind: String(kind).slice(0, 40),
    message: String(err.message || "").slice(0, 500),
    stack: [err.stack || "", extra.componentStack || ""]
      .filter(Boolean)
      .join("\n--- component stack ---\n")
      .slice(0, 2500),
    url: window.location.href.slice(0, 300),
  });
  try {
    fetch("/api/client-errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch((sendErr) => console.error("[report] отчёт об ошибке не отправлен", sendErr));
  } catch (sendErr) {
    console.error("[report] отчёт об ошибке не отправлен", sendErr);
  }
}
