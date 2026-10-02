# 📊 AUDIT REPORT: Fallbacks & Error Handling

Проект: Mebel Almaty (`my-site/`): Python-бэкенд на `http.server` + SQLite (`server.py`, `core/`, `features/`), React-фронтенд (`src/`).
Дата аудита: 01.10.2026. Номера строк соответствуют текущему состоянию файлов.

Уровни критичности: 🔴 критично · 🟠 высокий · 🟡 средний · 🟢 низкий.

> **Статус на 01.10.2026: все 16 фоллбеков (S-1…S-16), 13 пробелов (E-1…E-13) и 14 шагов плана исправлены — отметки `[DONE]`.**
> Фрагменты кода и номера строк ниже описывают состояние *до* исправлений. Что именно сделано — в разделе 5 в конце отчёта.

---

## 1. Резюме аудита

- **Всего проанализировано файлов: 69**
  (36 Python, 26 JS/JSX, 7 конфигов: `index.html`, `vite.config.js`, `package.json`, `requirements.txt`, `.env.example`, `.gitignore`, `start.bat`. `node_modules/`, `dist/`, `__pycache__/`, бинарные данные и `.env` с секретами не анализировались.)
- **Найдено критических заглушек/маскирующих фоллбеков: 16** (🔴 2 · 🟠 3 · 🟡 7 · 🟢 4)
- **Найдено дыр в обработке ошибок: 13** (🟠 3 · 🟡 4 · 🟢 6)

**Главные риски, коротко:**
1. Если ИИ-провайдер отвалится (истёк ключ, кончилась квота, сеть), сайт молча переходит на шаблонный бот: ответ отдаётся с `200 OK`, в шапке чата по-прежнему «онлайн», владелец ничего не узнаёт. Для фото шаблонный бот ещё и пишет «По изображению вижу…», хотя изображение никто не смотрел.
2. Кабинет показывает «Заказов пока нет» / «Клиентов пока нет», когда загрузка данных на самом деле упала: ошибка проглатывается пустым `catch(() => {})`.
3. Ошибки на сервере пишутся только через `print(str(err))`, без стека и без файла лога. Сбои резервного копирования тоже уходят только в консоль, которая закрывается вместе с окном `start.bat`.
4. `MEBEL_DATA_DIR` / `MEBEL_PORT` из `.env` молча игнорируются (файл читается уже после того, как эти значения вычислены), поэтому база может лежать не там, где ожидает владелец.

**Что сделано хорошо (правок не требует):** маркеров `TODO/FIXME/HACK/MOCK/STUB/TEMP/XXX` в коде проекта нет (совпадения `XXX` — это шаблон телефона `+7 XXX XXX-XX-XX`). Mock-данных в API нет. Запасного пароля в коде нет. Тела запросов валидируются (`read_json_body`). Цены заказа сервер пересчитывает по каталогу. Запись в БД идёт в транзакциях. Защита от path traversal и rate limits на месте. Корневой `ErrorBoundary` есть. Ошибки заказа (`CrmContext`) и чата показываются пользователю.

---

## 2. Критические заглушки и маскирующие фоллбеки

### [DONE] S-1 🔴 Молчаливый переход ИИ на шаблонный бот (LLM → local) с `200 OK`

- **Файл и строки:** `core/ai/llm.py:L66-L84`, `core/ai/engine.py:L54-L88`, `features/admin_status/__init__.py:L20-L30`, `src/components/ChatWidget.jsx:L486`, `L389-L401`
- **Тип проблемы:** Молчаливый return в catch → хардкод-фоллбек
- **Фрагмент кода:**

```python
# core/ai/llm.py
    except Exception as err:
        # Любой сбой сети/ответа должен уводить в локальный режим, а не в 500.
        return None, type(err).__name__

# core/ai/engine.py
    answer, whatsapp = local_reply(text, history, products, files)
    ...
    if status != "no_key":
        print(f"[ai] LLM недоступна ({status}), ответ из локального режима")
    result = {"reply": answer, "whatsapp": whatsapp, "mode": "local"}
```

```jsx
// ChatWidget.jsx
<p className="chat__status">Mebel Almaty · онлайн</p>
```

- **В чём риск на проде:** истёкший ключ (`http_401`), исчерпанная квота (`http_429`) или недоступный API превращают «ИИ-консультанта» в бота на ключевых словах, и это может длиться неделями. Ответ уходит с `200`, `mode: "local"` фронтенд игнорирует, шапка всё так же показывает «онлайн». Единственный след — строка `print` в консоли. `/api/ai-status` сообщает только `key_set` (ключ задан), но не то, работает ли он, и фронтенд этот эндпоинт нигде не вызывает. В `except Exception` попадают и баги в коде (`KeyError`, `TypeError`), они тоже маскируются без стека.
- **Предлагаемый Fix:**

```python
# core/ai/health.py (новый файл)
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_state = {"status": "unknown", "at": 0.0, "consecutive_failures": 0}


def record(status: str) -> None:
    with _lock:
        _state["status"] = status
        _state["at"] = time.time()
        _state["consecutive_failures"] = 0 if status in ("ok", "no_key") else _state["consecutive_failures"] + 1


def snapshot() -> dict:
    with _lock:
        return dict(_state)
```

```python
# core/ai/llm.py: логировать неожиданные исключения со стеком
import logging
log = logging.getLogger("ai.llm")
...
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return None, "empty"
    ...
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, UnicodeDecodeError) as err:
        return None, f"{type(err).__name__}: {err}"[:200]
    except Exception as err:
        log.exception("неожиданная ошибка вызова LLM")
        return None, type(err).__name__
```

```python
# core/ai/engine.py
import logging
from . import health
log = logging.getLogger("ai")
...
    llm, status = call_llm(settings, turns, system_extra, files)
    health.record(status)
    ...
    if status != "no_key":
        log.warning("LLM недоступна (%s), ответ из локального режима", status)
    result = {
        "reply": answer,
        "whatsapp": whatsapp,
        "mode": "local",
        "degraded": status != "no_key",
    }
```

```python
# features/admin_status/__init__.py: единый эндпоинт здоровья (используется и в E-2)
from core import db
from core.ai import health as ai_health

    def health(handler) -> None:
        settings = ai_settings(load_config())
        send_json(handler, {
            "ai": {"key_set": bool(settings["api_key"]), "model": settings["model"], **ai_health.snapshot()},
            "backup": db.backup_status(),
        })

    router.add("GET", "/api/admin/health", health, auth=True)
```

```jsx
// AdminPage.jsx: баннер над рабочим столом (<HealthBanner /> в начале <section id="desk">)
function HealthBanner() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/api/admin/health").then(setHealth).catch((err) => setError(err.message));
  }, []);
  const problems = [];
  if (error) problems.push(`Статус системы недоступен: ${error}`);
  if (health && !health.ai.key_set) problems.push("ИИ-консультант выключен (нет AI_API_KEY): гости получают шаблонные ответы.");
  if (health?.ai.consecutive_failures > 0)
    problems.push(`ИИ не отвечает (${health.ai.status}) ${health.ai.consecutive_failures} раз подряд: гости получают шаблонные ответы.`);
  if (health?.backup.ok === false) problems.push(`Резервная копия не создана: ${health.backup.error}`);
  if (!problems.length) return null;
  return (
    <div className="admin-health" role="alert">
      {problems.map((text) => <p key={text}>{text}</p>)}
    </div>
  );
}
```

```jsx
// ChatWidget.jsx: честный статус
const [degraded, setDegraded] = useState(false);
...
      setDegraded(Boolean(data.degraded));
...
<p className="chat__status">
  {degraded ? "Mebel Almaty · автоответчик, мастер ответит в WhatsApp" : "Mebel Almaty · онлайн"}
</p>
```

---

### [DONE] S-2 🔴 Кабинет показывает пустую CRM, когда загрузка упала

- **Файл и строки:** `src/pages/AdminPage.jsx:L379-L390`, `L392-L408`
- **Тип проблемы:** Пустой catch + `Promise.all` без обработки частичного сбоя
- **Фрагмент кода:**

```jsx
  const loadDesk = useCallback(async () => {
    const [p, o, c, ch] = await Promise.all([
      api("/api/admin/products"), api("/api/admin/orders"),
      api("/api/admin/clients"), api("/api/admin/chats"),
    ]);
    ...
  }, []);

    api("/api/session")
      .then(async (data) => {
        if (!data.ok) return;
        setAuthed(true);
        await loadDesk();
      })
      .catch(() => {});
```

- **В чём риск на проде:** если любой из четырёх запросов вернёт 500 (например, БД заблокирована или повреждён JSON в одной строке), `Promise.all` отклоняется целиком, а ошибку съедает `catch(() => {})`. При этом `authed` уже `true`, поэтому владелец видит рабочий стол с надписями «Заказов пока нет», «Клиентов пока нет», «Пока ничего нет. Добавьте первый товар» и делает вывод, что заявок нет. Если сервер недоступен на этапе `/api/session`, показывается форма входа без объяснения причины.
- **Предлагаемый Fix:**

```jsx
const [deskError, setDeskError] = useState("");

const loadDesk = useCallback(async () => {
  const results = await Promise.allSettled([
    api("/api/admin/products"),
    api("/api/admin/orders"),
    api("/api/admin/clients"),
    api("/api/admin/chats"),
  ]);
  const [p, o, c, ch] = results;
  if (p.status === "fulfilled") setProducts(p.value.products || []);
  if (o.status === "fulfilled") setOrders(o.value.orders || []);
  if (c.status === "fulfilled") setClients(c.value.clients || []);
  if (ch.status === "fulfilled") setChats(ch.value.chats || []);
  const failed = results.filter((r) => r.status === "rejected").map((r) => r.reason);
  if (failed.some((err) => err.status === 401)) {
    setAuthed(false);
    setLoginError("Сессия истекла, войдите снова.");
    return;
  }
  const names = ["товары", "заказы", "клиенты", "диалоги"].filter((_, i) => results[i].status === "rejected");
  setDeskError(names.length ? `Не загрузились: ${names.join(", ")}. ${failed[0].message}` : "");
}, []);

useEffect(() => {
  ...
  api("/api/session")
    .then(async (data) => {
      if (!data.ok) return;
      setAuthed(true);
      await loadDesk();
    })
    .catch((err) => setLoginError(`Сервер недоступен: ${err.message}`));
  ...
}, [loadDesk]);

// в разметке рабочего стола, сразу под <section id="desk">:
{deskError ? (
  <p className="form-error" role="alert">
    {deskError}{" "}
    <button className="btn btn--line" type="button" onClick={loadDesk}>Повторить</button>
  </p>
) : null}
```

---

### [DONE] S-3 🟠 Шаблонный бот утверждает, что «видит» фото, которое никто не анализировал

- **Файл и строки:** `core/ai/local.py:L22-L25`, `core/ai/attachments.py:L184`
- **Тип проблемы:** Хардкод-фоллбек (фейковый результат анализа)
- **Фрагмент кода:**

```python
        if images:
            bits.append(
                "По изображению вижу референс или планировку — для точной оценки размеров и материалов лучше продолжит мастер."
            )
```

- **В чём риск на проде:** без ключа или при сбое LLM клиент присылает, например, фото сломанной петли, а получает ответ «вижу референс или планировку». Это неправда клиенту и подрыв доверия. В записи вложения при этом стоит `parse_note: "vision: фото передано модели"`, даже если модель не вызывалась.
- **Предлагаемый Fix:**

```python
        if images:
            bits.append(
                "Фото сохранено. Автоматически разобрать его сейчас не получится — "
                "мастер посмотрит снимок лично и уточнит размеры и материалы."
            )
```

```python
# attachments.py, parse_bytes для изображений
            "parse_note": "фото сохранено",
```

---

### [DONE] S-4 🟠 Ошибка загрузки данных после входа пишется в скрытое поле

- **Файл и строки:** `src/pages/AdminPage.jsx:L463-L480`
- **Тип проблемы:** Маскирующий catch (ошибка уходит в невидимый UI)
- **Фрагмент кода:**

```jsx
    try {
      await api("/api/login", { ... });
      setAuthed(true);
      await loadDesk();
    } catch (err) {
      setLoginError(err.message);
    }
```

- **В чём риск на проде:** логин прошёл, `authed = true`, форма входа скрыта. Если `loadDesk()` падает, текст ошибки записывается в `loginError`, а он рендерится только внутри формы входа, которая уже не видна. Пользователь видит пустую CRM, как в S-2.
- **Предлагаемый Fix:**

```jsx
const handleLogin = async (event) => {
  event.preventDefault();
  setLoginError("");
  try {
    await api("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ login: event.target.login.value.trim(), password: event.target.password.value }),
    });
  } catch (err) {
    setLoginError(err.message);
    return;
  }
  setAuthed(true);
  await loadDesk(); // ошибки показывает сам loadDesk через deskError (см. S-2)
};
```

---

### [DONE] S-5 🟠 Переменные из `.env` для пути к данным и порта молча игнорируются; невалидированный env

- **Файл и строки:** `core/config.py:L10`, `L26`, `L131-L142`, `L182-L190`; `server.py:L25-L42`; `.env.example:L6`, `L12`
- **Тип проблемы:** Дефолтное значение маскирует ошибку конфигурации
- **Фрагмент кода:**

```python
# core/config.py: вычисляется при импорте модуля
DATA_DIR = Path(os.environ.get("MEBEL_DATA_DIR") or ROOT / "data").resolve()
PORT = int(os.environ.get("MEBEL_PORT") or 8780)

# server.py
from core import auth, db, settings   # ← здесь core.config уже импортирован
from core.config import (...)
...
load_dotenv()                          # ← .env читается только сейчас
```

- **В чём риск на проде:**
  - `MEBEL_DATA_DIR`, записанный в `.env`, не действует: база создаётся в `./data`, а владелец думает, что данные лежат, например, на диске `D:` под бэкапом. `MEBEL_PORT` из `.env` тоже игнорируется. Работают только системные переменные окружения.
  - `BACKUP_MIRROR_DIRS=...;%OneDrive%\MebelBackups`: если переменная `OneDrive` не определена, `os.path.expandvars` оставляет строку как есть. Получается относительный путь, и «облачные» копии тихо пишутся в папку `%OneDrive%` рядом с сервером.
  - `PHONE_E164` есть в `.env.example` и `.env`, но код его не читает: телефон захардкожен в трёх местах (`src/site.js`, `features/pdf/common.py`, `core/ai/prompt.py`). Если поменять номер в `.env`, ничего не изменится.
  - Невалидный `MEBEL_PORT=abc` роняет импорт голым `ValueError`. `AI_API_URL` и `TRUST_PROXY` не проверяются.
- **Предлагаемый Fix:**

```python
# core/config.py: загрузить .env ДО вычисления констант
ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def load_dotenv(path: Path = ENV_FILE) -> None:
    ...  # тело без изменений, функция переносится выше констант


load_dotenv()


def _env_port() -> int:
    raw = os.environ.get("MEBEL_PORT", "").strip()
    if not raw:
        return 8780
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise SystemExit(f"MEBEL_PORT={raw!r}: нужно число от 1 до 65535")
    return int(raw)


DATA_DIR = Path(os.environ.get("MEBEL_DATA_DIR") or ROOT / "data").resolve()
PORT = _env_port()
...


def validate_env() -> list[str]:
    problems: list[str] = []
    url = os.environ.get("AI_API_URL", "").strip()
    if url and not url.startswith("https://"):
        problems.append("AI_API_URL должен начинаться с https://")
    proxy = os.environ.get("TRUST_PROXY", "").strip().lower()
    if proxy not in {"", "0", "1", "true", "false", "yes", "no"}:
        problems.append(f"TRUST_PROXY={proxy!r}: допустимо 1 или 0")
    for folder in backup_mirror_dirs():
        if "%" in str(folder) or "$" in str(folder) or not folder.is_absolute():
            problems.append(f"BACKUP_MIRROR_DIRS: путь {folder} не раскрыт или не абсолютный — копии туда не попадут")
    return problems
```

```python
# server.py, main(): вызов load_dotenv() вверху файла удалить
    for problem in validate_env():
        log.error("Настройка .env: %s", problem)
```

Строку `PHONE_E164` из `.env.example` удалить или реально пробросить её в `pdf/common.py` и `prompt.py`.

---

### [DONE] S-6 🟡 `api()` в кабинете: ответ не в JSON превращается в «пустые данные», 401 не обрабатывается

- **Файл и строки:** `src/pages/AdminPage.jsx:L35-L40`
- **Тип проблемы:** Хардкод-фоллбек `{}` вместо ошибки
- **Фрагмент кода:**

```jsx
async function api(url, options = {}) {
  const response = await fetch(url, { credentials: "same-origin", ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Не получилось сохранить");
  return data;
}
```

- **В чём риск на проде:** если прокси или туннель (nginx, Cloudflare) вернёт `200` с HTML-страницей, `json()` падает, возвращается `{}`, и вызывающий код показывает `data.orders || []`, то есть пустой список. Сетевой сбой бросает `TypeError: Failed to fetch` без человеческого текста. Для ошибок загрузки (GET) текст по умолчанию «Не получилось сохранить» вводит в заблуждение. Истёкшая сессия (401) даёт только `alert("Нужен вход")`, а интерфейс остаётся в режиме рабочего стола.
- **Предлагаемый Fix:**

```jsx
class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function api(url, options = {}) {
  let response;
  try {
    response = await fetch(url, { credentials: "same-origin", ...options });
  } catch {
    throw new ApiError("Нет связи с сервером", 0);
  }
  const isJson = (response.headers.get("Content-Type") || "").includes("application/json");
  const data = isJson ? await response.json().catch(() => null) : null;
  if (!response.ok) throw new ApiError(data?.error || `Ошибка сервера (${response.status})`, response.status);
  if (data === null) throw new ApiError("Сервер вернул некорректный ответ", response.status);
  return data;
}
```

Плюс в кнопках «Обновить» и обработчиках: `if (err.status === 401) { setAuthed(false); return; }`.

---

### [DONE] S-7 🟡 Кнопка «Обновить» заказы стирает список при ошибке

- **Файл и строки:** `src/pages/AdminPage.jsx:L707-L715`
- **Тип проблемы:** Молчаливый фоллбек `[]` в catch
- **Фрагмент кода:**

```jsx
                    try {
                      const data = await api("/api/admin/orders");
                      setOrders(data.orders || []);
                    } catch (err) {
                      setOrders([]);
                      alert(err.message);
                    }
```

- **В чём риск на проде:** при кратковременном сбое сети уже загруженные заказы исчезают с экрана, и после закрытия alert остаётся «Заказов пока нет».
- **Предлагаемый Fix:**

```jsx
                    try {
                      const data = await api("/api/admin/orders");
                      setOrders(data.orders || []);
                    } catch (err) {
                      if (err.status === 401) { setAuthed(false); return; }
                      setDeskError(`Заказы не обновились: ${err.message}. Показан прошлый список.`);
                    }
```

---

### [DONE] S-8 🟡 Витрина: dev-подсказка для покупателей и «пусто» вместо ошибки

- **Файл и строки:** `src/components/ShopGrid.jsx:L17-L47`
- **Тип проблемы:** Хардкод-заглушка в проде
- **Фрагмент кода:**

```jsx
        const list = Array.isArray(data.products) ? data.products : [];
        ...
      } catch {
        if (!cancelled) {
          setStatusHidden(false);
          setStatus("Каталог откроется, когда сайт запущен через server.py — двойной щелчок по start.bat.");
        }
      }
```

- **В чём риск на проде:** при любом сбое API покупатель видит инструкцию для разработчика про `server.py` и `start.bat`. Если ответ пришёл в неверном формате, показывается «Пока нет готовых изделий», и сбой маскируется под пустую витрину. Кнопки «Повторить» нет, ошибка нигде не логируется.
- **Предлагаемый Fix:**

```jsx
  const [loadError, setLoadError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch("/api/products");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (!Array.isArray(data?.products)) throw new Error("Некорректный ответ /api/products");
        if (cancelled) return;
        setLoadError(false);
        setProducts(data.products);
        ...
      } catch (err) {
        if (cancelled) return;
        console.error("Витрина не загрузилась:", err);
        setLoadError(true);
        setStatusHidden(false);
        setStatus("Не удалось загрузить витрину. Обновите страницу или напишите нам в WhatsApp — пришлём каталог.");
      }
    })();
    return () => { cancelled = true; };
  }, [limit, reloadKey]);
  ...
  {loadError ? (
    <button className="btn btn--line" type="button" onClick={() => setReloadKey((k) => k + 1)}>Повторить</button>
  ) : null}
```

---

### [DONE] S-9 🟡 Повреждённый JSON в БД молча заменяется пустым значением

- **Файл и строки:** `core/db.py:L119-L125`; используется в `features/crm/service.py:L112`, `features/catalog/service.py:L57`, `features/chat/service.py:L43`, `core/settings.py:L42`, `L111`
- **Тип проблемы:** Молчаливый return в catch
- **Фрагмент кода:**

```python
def loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback
```

- **В чём риск на проде:** если `orders.items` повреждён, заказ в CRM показывается без позиций, а счёт печатается одной строкой «Работы по заявке» с итогом «по согласованию», хотя в заказе были товары с ценами. Никакого лога нет, найти причину невозможно.
- **Предлагаемый Fix:**

```python
import logging
log = logging.getLogger("db")


def loads(value: str | None, fallback: Any, *, context: str = "") -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError) as err:
        log.error("повреждённый JSON%s: %s; начало значения: %.80r", f" ({context})" if context else "", err, value)
        return fallback
```

```python
# features/crm/service.py, _order_from_row
    items = loads(row["items"], None, context=f"orders.items id={row['id']}")
    return {
        ...
        "items": items if isinstance(items, list) else [],
        "items_corrupted": items is None and bool(row["items"]),
    }
```

```python
# features/pdf/__init__.py, order_invoice
        if order.get("items_corrupted"):
            send_json(handler, {"error": "Позиции заказа повреждены — счёт не сформирован. Восстановите заказ из резервной копии."}, 409)
            return
```

---

### [DONE] S-10 🟡 В счёт по умолчанию попадают «Без НДС», Кбе 19 и КНП 710

- **Файл и строки:** `core/settings.py:L72`, `L75`; `features/pdf/invoice_pdf.py:L263-L272`, `L345-L349`
- **Тип проблемы:** Хардкод-фоллбек в финансовом документе
- **Фрагмент кода:**

```python
SELLER_DEFAULTS: dict[str, str] = {field: "" for field in SELLER_FIELDS} | {"kbe": "19", "knp": "710", "vat_note": "Без НДС"}
SELLER_REQUIRED = ("name", "bin", "iban", "bank", "bik")
```

- **В чём риск на проде:** если владелец заполнил пять обязательных полей, пометка «ОБРАЗЕЦ» пропадает, а налоговая отметка «Без НДС» и коды Кбе/КНП печатаются из хардкода, хотя владелец их не вводил. Для плательщика НДС это некорректный счёт; неверный Кбе/КНП может привести к возврату платежа банком.
- **Предлагаемый Fix:**

```python
SELLER_DEFAULTS: dict[str, str] = {field: "" for field in SELLER_FIELDS}

SELLER_REQUIRED = ("name", "bin", "iban", "bank", "bik", "kbe", "knp", "vat_note")
```

В `AdminPage.jsx` (`SELLER_FIELDS`) для `kbe`, `knp`, `vat_note` поставить `required: true`. Плейсхолдеры `19` / `710` / `Без НДС` оставить как подсказки.

---

### [DONE] S-11 🟡 Счёт с повреждённой датой заказа получает сегодняшнюю дату

- **Файл и строки:** `features/pdf/common.py:L55-L63`; `features/pdf/invoice_pdf.py:L397`
- **Тип проблемы:** Хардкод-фоллбек в финансовом документе
- **Фрагмент кода:**

```python
def shop_date(raw) -> str:
    """ISO-время из БД (UTC) → дата магазина; без зоны считаем UTC. Пусто/мусор → сегодня."""
    try:
        moment = datetime.fromisoformat(str(raw or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return today()
```

- **В чём риск на проде:** дата счёта меняется при каждой генерации, так что один и тот же номер счёта выходит с разными датами. Это расхождение в бухгалтерских документах, и в логах о нём ничего нет.
- **Предлагаемый Fix:**

```python
def shop_date(raw) -> str:
    text = str(raw or "").strip()
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as err:
        raise ValueError(f"Некорректная дата документа: {text!r}") from err
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return f"{moment.astimezone(SHOP_TZ):%d.%m.%Y}"
```

```python
# features/pdf/__init__.py, order_invoice
        try:
            pdf = build_invoice_pdf(order)
        except ValueError as err:
            log.error("счёт по заказу %s не собран: %s", order.get("id"), err)
            send_json(handler, {"error": "У заказа повреждены данные — счёт не сформирован."}, 409)
            return
        send_bytes(handler, pdf, filename=f"invoice_{invoice_number(order)}.pdf")
```

---

### [DONE] S-12 🟡 Каталог: невалидные поля товара молча подменяются, ответ `200 OK`

- **Файл и строки:** `features/catalog/service.py:L182-L211`; `features/catalog/__init__.py:L46-L54`
- **Тип проблемы:** Молчаливое приведение данных (silent coercion)
- **Фрагмент кода:**

```python
    title = str(body.get("title", item.get("title", ""))).strip()
    if len(title) >= 2:
        item["title"] = title[:120]          # короткое название молча игнорируется
    ...
    try:
        item["qty"] = min(MAX_QTY, max(1, int(raw_qty)))
    except (TypeError, ValueError, OverflowError):
        item["qty"] = item.get("qty", 1)     # мусор → старое значение
    ...
        try:
            item["price"] = min(MAX_PRICE, int(raw_price))
        except (TypeError, ValueError, OverflowError):
            item["price"] = item.get("price")  # мусор → старая цена / «по запросу»
```

- **В чём риск на проде:** админ вводит цену `185 000` (с пробелом) или `185000.50`, получает «Сохранено», а на сайте остаётся старая цена или появляется «цена по запросу». Неизвестная валюта или раздел молча превращаются в `KZT` / `Другое`. `PUT /api/products/:id` вообще не возвращает 400.
- **Предлагаемый Fix:**

```python
CATEGORIES = {"Шкафы", "Кровати", "Кухни", "Другое"}
KINDS = {"Товар", "Услуга"}
CURRENCIES = {"KZT", "USD", "RUB"}


def _parse_int(raw, label: str, *, minimum: int, maximum: int, allow_empty: bool) -> int | None:
    if raw in ("", None):
        if allow_empty:
            return None
        raise ValueError(f"{label}: укажите число")
    if isinstance(raw, bool):
        raise ValueError(f"{label}: нужно целое число")
    try:
        value = int(str(raw).replace(" ", "").strip())
    except ValueError:
        raise ValueError(f"{label}: нужно целое число") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{label}: от {minimum} до {maximum}")
    return value


def _choice(body: dict, key: str, allowed: set[str], label: str, current: str) -> str:
    if key not in body:
        return current
    value = str(body[key])
    if value not in allowed:
        raise ValueError(f"{label}: недопустимое значение «{value}»")
    return value


def apply_fields(item: dict, body: dict) -> None:
    if "title" in body:
        title = str(body.get("title") or "").strip()
        if len(title) < 2:
            raise ValueError("Название: минимум 2 символа")
        item["title"] = title[:120]
    item["category"] = _choice(body, "category", CATEGORIES, "Раздел", item.get("category", "Другое"))
    item["kind"] = _choice(body, "kind", KINDS, "Тип", item.get("kind", "Товар"))
    item["currency"] = _choice(body, "currency", CURRENCIES, "Валюта", item.get("currency", "KZT"))
    if "qty" in body:
        item["qty"] = _parse_int(body["qty"], "Количество", minimum=1, maximum=MAX_QTY, allow_empty=False)
    if "price" in body:
        item["price"] = _parse_int(body["price"], "Цена", minimum=0, maximum=MAX_PRICE, allow_empty=True) or None
    if "description" in body:
        item["description"] = str(body.get("description") or "")[:500]
    if "visible" in body:
        item["visible"] = bool(body["visible"])
    ...  # блок images/image без изменений
```

```python
# features/catalog/__init__.py, update
        try:
            item = service.update_product(product_id, body)
        except ValueError as err:
            send_json(handler, {"error": str(err)}, 400)
            return
```

---

### [DONE] S-13 🟢 Пароль администратора может браться из БД в открытом виде

- **Файл и строки:** `core/config.py:L148-L157`
- **Тип проблемы:** Скрытый фоллбек источника учётных данных
- **Фрагмент кода:**

```python
    login = str(os.environ.get("ADMIN_LOGIN") or config.get("login") or "").strip()
    password = str(os.environ.get("ADMIN_PASSWORD") or config.get("password") or "")
```

- **В чём риск на проде:** если `ADMIN_PASSWORD` в `.env` пуст или удалён, вход молча продолжает работать по старому паролю из таблицы `settings`. Он хранится открытым текстом и попадает во все резервные копии в `data/backups/` и в зеркала, в том числе в OneDrive.
- **Предлагаемый Fix:**

```python
def credentials() -> tuple[str, str] | None:
    """Логин и пароль только из .env. None — вход в кабинет закрыт."""
    login = os.environ.get("ADMIN_LOGIN", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not login or len(password) < MIN_PASSWORD_LENGTH:
        return None
    return login, password
```

```python
# core/settings.py, setup(): одноразово вычистить пароль из БД
    with transaction() as conn:
        if conn.execute("DELETE FROM settings WHERE key IN ('login', 'password')").rowcount:
            log.warning("Логин/пароль удалены из базы — задайте ADMIN_LOGIN и ADMIN_PASSWORD в .env")
```

---

### [DONE] S-14 🟢 Корзина: неудачная сверка с каталогом проходит молча

- **Файл и строки:** `src/context/CartContext.jsx:L58-L67`
- **Тип проблемы:** Молчаливый return в catch
- **Фрагмент кода:**

```jsx
    try {
      const response = await fetch("/api/products");
      if (!response.ok) return;
      ...
    } catch {
      return;
    }
```

- **В чём риск на проде:** покупатель видит устаревшие цены. Сервер пересчитывает цены в записи заказа, но текст WhatsApp-сообщения мастеру (`cartText`) собирается из клиентских цен, так что мастер видит неактуальную сумму.
- **Предлагаемый Fix:**

```jsx
    try {
      const response = await fetch("/api/products");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      products = Array.isArray(data.products) ? data.products : null;
      if (!products) throw new Error("Некорректный ответ каталога");
    } catch (err) {
      console.warn("Сверка корзины с каталогом не удалась:", err);
      if (itemsRef.current.length) setNotice("Не удалось сверить цены с каталогом — итоговую сумму подтвердит мастер.");
      return;
    }
```

---

### [DONE] S-15 🟢 PDF: битое или пропавшее фото товара тихо становится «фото по запросу»

- **Файл и строки:** `features/pdf/catalog_pdf.py:L74-L95`; `features/pdf/common.py:L141-L152`
- **Тип проблемы:** Молчаливый return None
- **Фрагмент кода:**

```python
    if not path.is_file():
        return None
    try:
        ...
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
```

- **В чём риск на проде:** потеря файлов в `assets/products/` (сбой диска, ручное удаление) не видна нигде: в публичном PDF-каталоге просто печатается «фото по запросу». Логотип пропадает из счетов так же незаметно.
- **Предлагаемый Fix:**

```python
log = logging.getLogger("pdf")
...
    if not path.is_file():
        log.warning("фото товара отсутствует: %s", relative_path)
        return None
    try:
        ...
    except (OSError, ValueError, Image.DecompressionBombError) as err:
        log.warning("фото товара не читается: %s (%s)", relative_path, err)
        return None
```

Аналогично в `_load_logo`: `log.error("логотип %s не загружен: %s", path, err)`.

---

### [DONE] S-16 🟢 Портфолио на главной состоит из заглушек

- **Файл и строки:** `src/pages/HomePage.jsx:L77-L86`, `L151-L166`, `L320-L334`
- **Тип проблемы:** Хардкод-данные (плейсхолдеры в проде)
- **Фрагмент кода:**

```jsx
  const works = [
    { cls: "shot shot--a", frame: "g-navy", seam: "seam--doors", idx: "01", title: "Встроенный шкаф", sub: "Ниша у окна · матовый шпон" },
    ...
  ];
```

- **В чём риск на проде:** раздел «04 — Портфолио» и кадр в hero («Интерьерный кадр») показывают CSS-градиенты и SVG-эскиз вместо реальных работ. Для мебельного ателье это прямой риск конверсии: посетитель видит пустые рамки с подписями. Фотографии `assets/inbox/WhatsApp Image *.jpeg` в проекте уже лежат, но нигде не используются.
- **Предлагаемый Fix:** вынести данные в `src/data/works.js` с полем `image`, показывать фото и скрывать карточки без него:

```jsx
// src/data/works.js
export const WORKS = [
  { idx: "01", title: "Встроенный шкаф", sub: "Ниша у окна · матовый шпон", image: "/assets/works/01.jpg" },
  // ...
];

// HomePage.jsx
import { WORKS } from "../data/works";
const works = WORKS.filter((item) => item.image);
...
{works.length ? (
  <div className="feed">
    {works.map((item) => (
      <figure className="shot reveal" key={item.idx}>
        <img className="shot__frame" src={item.image} alt={item.title} loading="lazy" />
        <figcaption><strong>{item.title}</strong><span>{item.sub}</span></figcaption>
      </figure>
    ))}
  </div>
) : null}
```

---

## 3. Пробелы в обработке ошибок

### [DONE] E-1 🟠 Ошибки сервера: только `print(str(err))`, нет стека и файла лога, бывает двойной ответ

- **Файл и строки:** `core/router.py:L73-L90`; `server.py:L129-L130`; в целом весь бэкенд (модуль `logging` не используется ни в одном файле)
- **Тип проблемы:** catch только с `print` / потеря диагностики
- **Фрагмент кода:**

```python
            try:
                ...
                route.fn(handler)
            except Exception as err:
                print(f"[router] {method} {path}: {err}")
                send_json(handler, {"error": "Внутренняя ошибка сервера"}, 500)
            return True
```

- **Почему это проблема:**
  1. В лог попадает только текст исключения: для `KeyError('id')` это буквально `'id'`, без файла, строки и стека.
  2. Все логи идут в stdout окна `start.bat`. После закрытия окна или перезагрузки ПК история ошибок, неудачных входов и сбоев ИИ и бэкапов теряется.
  3. Если исключение возникло после `send_response` (например, клиент закрыл вкладку во время `send_bytes` PDF), роутер пытается отправить второй ответ поверх первого. Это даёт новое исключение, которое уходит в `socketserver.handle_error`.
- **Предлагаемый Fix:**

```python
# core/router.py
import logging

log = logging.getLogger("router")
_CLIENT_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


def _fail(handler) -> None:
    if getattr(handler, "response_started", False):
        handler.close_connection = True
        return
    try:
        send_json(handler, {"error": "Внутренняя ошибка сервера"}, 500)
    except _CLIENT_GONE:
        handler.close_connection = True

...
            try:
                if route.prefix is not None:
                    route.fn(handler, rest)
                else:
                    route.fn(handler)
            except _CLIENT_GONE:
                handler.close_connection = True
            except Exception:
                log.exception("%s %s", method, path)
                _fail(handler)
            return True

        for route in catch_alls:
            try:
                if route.fn(handler, path):
                    return True
            except _CLIENT_GONE:
                handler.close_connection = True
                return True
            except Exception:
                log.exception("catch-all %s %s", method, path)
                _fail(handler)
                return True
        return False
```

```python
# server.py
import logging
from logging.handlers import RotatingFileHandler
from core.config import DATA_DIR

log = logging.getLogger("server")


def setup_logging() -> None:
    log_dir = DATA_DIR / "logs"          # /data/* закрыт для HTTP через is_blocked
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(log_dir / "server.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"),
        ],
    )


class ShopHandler(SimpleHTTPRequestHandler):
    response_started = False

    def send_response(self, code, message=None):
        self.response_started = True
        super().send_response(code, message)

    def _dispatch(self, method: str) -> bool:
        self.response_started = False
        ...

    def log_message(self, fmt: str, *args) -> None:
        logging.getLogger("http").info(fmt, *args)


def main() -> None:
    setup_logging()
    ...
```

Все остальные `print(f"[...] ...")` в `core/` и `features/` заменить на `logging.getLogger(<модуль>).warning/error(...)`.

---

### [DONE] E-2 🟠 Сбои резервного копирования видны только в консоли; остаются битые копии

- **Файл и строки:** `core/db.py:L214-L220`, `L223-L231`, `L234-L250`, `L261-L275`
- **Тип проблемы:** Пустой catch (`pass`) / catch только с `print` / нет нотификации
- **Фрагмент кода:**

```python
def _rotate(folder: Path, reason: str) -> None:
    ...
        try:
            old.unlink()
        except OSError:
            pass

def start_backup_scheduler(interval_hours: float = 24.0) -> None:
    def loop() -> None:
        while True:
            time.sleep(interval_hours * 3600)
            try:
                backup("daily")
            except Exception as err:
                print(f"[db] резервная копия не создана: {err}")
```

- **Почему это проблема:** если диск переполнен, флешка вынута или OneDrive недоступен, ежедневные копии перестают создаваться, а владелец узнаёт об этом только при попытке восстановления. Если `source.backup(dest)` упал на середине, недописанный файл `shop-...-daily.db` остаётся в папке и участвует в ротации, вытесняя рабочие копии. Ошибки `_rotate` глотаются полностью, и старые копии могут копиться до заполнения диска.
- **Предлагаемый Fix:**

```python
import logging
log = logging.getLogger("db")

_BACKUP_STATE: dict = {"ok": None, "at": "", "error": "", "mirrors_failed": []}
_BACKUP_LOCK = threading.Lock()


def backup_status() -> dict:
    with _BACKUP_LOCK:
        return dict(_BACKUP_STATE)


def _rotate(folder: Path, reason: str) -> None:
    copies = sorted(folder.glob(f"shop-*-{reason}.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in copies[BACKUP_KEEP:]:
        try:
            old.unlink()
        except OSError as err:
            log.warning("старая копия %s не удалена: %s", old, err)


def _mirror(target: Path, reason: str) -> list[str]:
    failed: list[str] = []
    for folder in backup_mirror_dirs():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, folder / target.name)
            _rotate(folder, reason)
        except OSError as err:
            log.error("копия в %s не создана: %s", folder, err)
            failed.append(f"{folder}: {err}")
    return failed


def backup(reason: str = "auto") -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"shop-{stamp}-{reason}.db"
    try:
        source = _connect()
        try:
            dest = sqlite3.connect(target)
            try:
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()
    except Exception as err:
        target.unlink(missing_ok=True)
        with _BACKUP_LOCK:
            _BACKUP_STATE.update(ok=False, at=utc_now(), error=str(err))
        raise
    _rotate(BACKUP_DIR, reason)
    failed = _mirror(target, reason)
    with _BACKUP_LOCK:
        _BACKUP_STATE.update(ok=True, at=utc_now(), error="", mirrors_failed=failed)
    return target


def start_backup_scheduler(interval_hours: float = 24.0) -> None:
    def loop() -> None:
        while True:
            time.sleep(interval_hours * 3600)
            try:
                backup("daily")
            except Exception:
                log.exception("резервная копия не создана")
            for name, task in _MAINTENANCE:
                try:
                    task()
                except Exception:
                    log.exception("обслуживание %s", name)

    threading.Thread(target=loop, name="db-backup", daemon=True).start()
```

Статус выводится в кабинете через `/api/admin/health` и `HealthBanner` (см. S-1). В баннер стоит добавить и `mirrors_failed`.

---

### [DONE] E-3 🟠 Вложения чата: zip-бомба в .docx/.xlsx и молчаливые сбои разбора

- **Файл и строки:** `core/ai/attachments.py:L82-L93`, `L96-L134`, `L189-L193`, `L205-L209`, `L221-L225`
- **Тип проблемы:** Нет валидации входных данных + пустой catch
- **Фрагмент кода:**

```python
def extract_docx(raw: bytes) -> str:
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        xml = archive.read("word/document.xml")    # размер после распаковки не ограничен
...
        try:
            text = extract_docx(raw)[:MAX_TEXT]
        except Exception:
            text = ""
```

- **Почему это проблема:** эндпоинт `/api/chat` публичный. Файл `.docx` размером до 4 МБ с сильно сжатым `document.xml` распаковывается в гигабайты прямо в памяти, а `ElementTree` строит из них дерево. Три таких файла в одном запросе и 12 запросов в минуту с одного IP способны исчерпать RAM и уронить процесс. Отдельно: любые ошибки разбора (включая баги) глотаются без лога, а клиент видит «возможно скан».
- **Предлагаемый Fix:**

```python
import logging
log = logging.getLogger("ai.attachments")

MAX_UNZIPPED = 20 * 1024 * 1024
MAX_ZIP_ENTRIES = 2000


def _open_zip(raw: bytes) -> zipfile.ZipFile:
    archive = zipfile.ZipFile(BytesIO(raw))
    if len(archive.infolist()) > MAX_ZIP_ENTRIES:
        archive.close()
        raise ValueError("слишком много файлов внутри документа")
    return archive


def _read_member(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > MAX_UNZIPPED:
        raise ValueError(f"{name}: после распаковки {info.file_size} байт, лимит {MAX_UNZIPPED}")
    return archive.read(name)   # ZipExtFile не распакует больше file_size


def extract_docx(raw: bytes) -> str:
    with _open_zip(raw) as archive:
        xml = _read_member(archive, "word/document.xml")
    ...

# extract_xlsx: zipfile.ZipFile(...) → _open_zip(raw), archive.read(...) → _read_member(archive, ...)

# parse_bytes: во всех трёх ветках
        except Exception as err:
            log.warning("%s не разобран (%s): %s", safe, mime, err)
            text = ""
```

---

### [DONE] E-4 🟡 Чат: потерянные вложения не показываются клиенту, если есть текст

- **Файл и строки:** `core/ai/attachments.py:L376-L387`; `features/chat/__init__.py:L41-L46`; `src/components/ChatWidget.jsx:L383-L402`
- **Тип проблемы:** Ошибка проглатывается, ответ `200 OK`
- **Фрагмент кода:**

```python
        attachments, attach_error = service.process_chat_attachments(raw_attachments)
        if not message and not attachments:
            err = attach_error or "Напишите сообщение или прикрепите файл"
            send_json(handler, {"error": err}, 400)
            return
        # если message непустой — attach_error дальше нигде не используется
```

- **Почему это проблема:** клиент пишет «вот план кухни» и прикладывает файл. Файл не прошёл (больше 4 МБ, переполнена папка, битый base64), но текст есть, поэтому ИИ отвечает, а `attach_error` теряется. Клиент уверен, что план отправлен. То же при частичном успехе: из трёх файлов принят один, а `ingest_attachments` возвращает `""`. Поле `attachments` в ответе фронтенд не читает.
- **Предлагаемый Fix:**

```python
# core/ai/attachments.py, конец ingest_attachments
    skipped = skipped_empty + skipped_big + skipped_bad + skipped_quota
    extra = max(0, len(raw_items) - 3)
    if prepared:
        notes = []
        if skipped:
            notes.append(f"Принято файлов: {len(prepared)} из {len(prepared) + skipped}, остальные не удалось прочитать.")
        if extra:
            notes.append(f"Не отправлено файлов сверх лимита (3): {extra}.")
        return prepared, " ".join(notes)
```

```python
# features/chat/__init__.py, перед send_json(handler, result)
        if attach_error:
            result["attachment_warning"] = attach_error
```

```jsx
// ChatWidget.jsx, после добавления ответа бота
      if (data.attachment_warning) {
        setMessages((prev) => [...prev, { id: nextId("w"), role: "bot", text: data.attachment_warning }]);
      }
```

---

### [DONE] E-5 🟡 Фронтенд: один корневой Error Boundary, необработанные rejection не перехватываются, отчётов нет

- **Файл и строки:** `src/main.jsx:L9-L17`; `src/App.jsx:L11-L22`; `src/components/ErrorBoundary.jsx:L14-L16`
- **Тип проблемы:** Нет Error Boundaries по зонам / Unhandled Promise / catch только с `console.error`
- **Фрагмент кода:**

```jsx
  componentDidCatch(error, info) {
    console.error("UI error:", error, info?.componentStack);
  }
```

- **Почему это проблема:** ошибка рендера в `ChatWidget` или `Cart` (например, неожиданный формат ответа) сносит весь сайт до экрана «Что-то пошло не так», хотя витрина и форма заявки могли бы работать дальше. Ошибки в async-обработчиках (`onClick={async …}`) Error Boundary не ловит, а глобального `unhandledrejection` нет. Владелец ни об одной ошибке у посетителей не узнаёт: отчёт уходит только в консоль браузера клиента.
- **Предлагаемый Fix:**

```js
// src/utils/report.js
export function reportClientError(error, extra = {}) {
  console.error("UI error:", error, extra);
  try {
    const body = JSON.stringify({
      message: String(error?.message || error).slice(0, 500),
      stack: String(error?.stack || "").slice(0, 2000),
      url: window.location.pathname,
      ...extra,
    });
    navigator.sendBeacon?.("/api/client-errors", new Blob([body], { type: "application/json" }));
  } catch {
    /* отчёт об ошибке не должен сам ронять страницу */
  }
}
```

```jsx
// ErrorBoundary.jsx
import { reportClientError } from "../utils/report";
...
  componentDidCatch(error, info) {
    reportClientError(error, { scope: this.props.scope || "root", componentStack: info?.componentStack?.slice(0, 2000) });
  }

  render() {
    if (!this.state.failed) return this.props.children;
    if (this.props.fallback !== undefined) return this.props.fallback;
    return ( /* текущий полноэкранный экран ошибки */ );
  }
```

```jsx
// main.jsx
import { reportClientError } from "./utils/report";
window.addEventListener("unhandledrejection", (event) => reportClientError(event.reason, { scope: "unhandledrejection" }));
window.addEventListener("error", (event) => reportClientError(event.error || event.message, { scope: "window.error" }));

// App.jsx
      <Route path="/admin" element={<ErrorBoundary scope="admin"><AdminPage /></ErrorBoundary>} />
...
        <ErrorBoundary scope="cart" fallback={null}><Cart /></ErrorBoundary>
        <ErrorBoundary scope="chat" fallback={null}><ChatWidget /></ErrorBoundary>
```

```python
# features/admin_status/__init__.py: приём отчётов (публичный, с лимитом)
import logging
CLIENT_ERRORS = RateLimiter(20, 60.0)
client_log = logging.getLogger("client")

    def client_error(handler) -> None:
        if not CLIENT_ERRORS.allow(client_ip(handler)):
            send_json(handler, {"ok": False}, 429)
            return
        body = read_json_body(handler, 8_000)
        if body is None:
            return
        client_log.warning("frontend [%s] %s: %s", str(body.get("scope"))[:40], str(body.get("url"))[:200], str(body.get("message"))[:500])
        send_json(handler, {"ok": True})

    router.add("POST", "/api/client-errors", client_error)
```

---

### [DONE] E-6 🟡 Реестр ИИ-инструментов глотает исключения без лога

- **Файл и строки:** `core/ai/tools.py:L29-L48`
- **Тип проблемы:** Пустой catch (`except Exception: continue`)
- **Фрагмент кода:**

```python
            try:
                chunk = tool.context(products, history)
            except Exception:
                continue
```

- **Почему это проблема:** если сломается `CatalogTool` (например, у товара `price` не того типа), каталог молча исчезнет из system prompt, и ИИ начнёт отвечать «на витрине пусто» или выдумывать товары. Обнаружить это невозможно. `run_actions` нигде не вызывается — это мёртвый код.
- **Предлагаемый Fix:**

```python
import logging
log = logging.getLogger("ai.tools")
...
            try:
                chunk = tool.context(products, history)
            except Exception:
                log.exception("инструмент %s: context() упал, блок пропущен", getattr(tool, "name", tool))
                continue
```

`run_actions` либо удалить, либо добавить в него такой же `log.exception`.

---

### [DONE] E-7 🟡 Выход из кабинета: необработанное отклонение промиса

- **Файл и строки:** `src/pages/AdminPage.jsx:L482-L486`
- **Тип проблемы:** Unhandled Promise
- **Фрагмент кода:**

```jsx
  const handleLogout = async () => {
    closeForm();
    await api("/api/logout", { method: "POST" });
    setAuthed(false);
  };
```

- **Почему это проблема:** при сбое сети промис отклоняется без обработки. Кнопка «Выйти» ничего не делает и ничего не сообщает, сессия на сервере остаётся живой. Это важно, если кабинет открыт на чужом компьютере.
- **Предлагаемый Fix:**

```jsx
  const handleLogout = async () => {
    closeForm();
    try {
      await api("/api/logout", { method: "POST" });
    } catch (err) {
      alert(`Сервер не подтвердил выход: ${err.message}. Закройте браузер, чтобы сессия точно завершилась.`);
    } finally {
      setAuthed(false);
    }
  };
```

---

### [DONE] E-8 🟢 Квота папки вложений: ошибка чтения означает «0 байт занято»

- **Файл и строки:** `core/ai/attachments.py:L276-L280`
- **Тип проблемы:** Молчаливый fallback, снимающий защиту
- **Фрагмент кода:**

```python
def _chat_dir_size() -> int:
    try:
        return sum(p.stat().st_size for p in CHAT_DIR.iterdir() if p.is_file())
    except OSError:
        return 0
```

- **Почему это проблема:** если папку не удалось прочитать (антивирус держит файл, файл удалён во время обхода), квота в 500 МБ считается пустой, и защита от переполнения диска не срабатывает.
- **Предлагаемый Fix:**

```python
def _chat_dir_size() -> int:
    try:
        return sum(p.stat().st_size for p in CHAT_DIR.iterdir() if p.is_file())
    except OSError as err:
        log.error("размер %s не посчитан (%s) — считаю папку заполненной", CHAT_DIR, err)
        return CHAT_DIR_QUOTA
```

---

### [DONE] E-9 🟢 `PATCH /api/orders/:id` требует статус даже для обновления одной заметки

- **Файл и строки:** `features/crm/__init__.py:L41-L54`; `features/crm/service.py:L374-L386`
- **Тип проблемы:** Неверная валидация payload (вводящий в заблуждение 400)
- **Фрагмент кода:**

```python
        status = str(body.get("status") or "").strip().lower()
        ...
def patch_order(order_id: str, status: str, note) -> dict | None:
    if status not in ORDER_STATUSES:
        raise ValueError("Неверный статус")
```

- **Предлагаемый Fix:**

```python
# __init__.py
        status = str(body["status"]).strip().lower() if "status" in body else None

# service.py
def patch_order(order_id: str, status: str | None, note) -> dict | None:
    if status is not None and status not in ORDER_STATUSES:
        raise ValueError("Неверный статус")
    if status is None and note is None:
        raise ValueError("Нечего обновлять")
    with transaction() as conn:
        if _get_order(conn, order_id) is None:
            return None
        if status is not None:
            conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        if note is not None:
            conn.execute("UPDATE orders SET note = ? WHERE id = ?", (str(note)[:1000], order_id))
        conn.execute("UPDATE orders SET updated_at = ? WHERE id = ?", (utc_now(), order_id))
        return _get_order(conn, order_id)
```

---

### [DONE] E-10 🟢 Проверка сессии для `/assets/chat/` вне обработчика ошибок

- **Файл и строки:** `server.py:L94-L96`
- **Тип проблемы:** Uncaught Exception (соединение рвётся без ответа)
- **Фрагмент кода:**

```python
        if normalize_request_path(path).startswith("/assets/chat/") and not auth.authorized(self):
            self.send_error(404)
            return True
```

- **Почему это проблема:** `authorized()` обращается к SQLite. Если база заблокирована дольше 30 секунд, исключение уходит в `socketserver.handle_error`: стек печатается в консоль, а браузер админа получает обрыв соединения вместо осмысленного ответа.
- **Предлагаемый Fix:**

```python
        if normalize_request_path(path).startswith("/assets/chat/"):
            try:
                allowed = auth.authorized(self)
            except Exception:
                log.exception("проверка сессии для %s", path)
                self.send_error(503)
                return True
            if not allowed:
                self.send_error(404)
                return True
```

---

### [DONE] E-11 🟢 Чат: файлы остаются на диске, если запрос упал после их сохранения

- **Файл и строки:** `features/chat/__init__.py:L42-L63`; `core/ai/attachments.py:L369-L372`
- **Тип проблемы:** Нет компенсации при исключении
- **Почему это проблема:** вложения записываются в `assets/chat/` до вызова ИИ и записи в БД. Если `append_chat_turn` упал (БД заблокирована), клиент получает 500, фронтенд возвращает файлы в очередь, и при повторной отправке на диск ложится дубликат. Файлы от неудачных попыток не связаны ни с одним диалогом.
- **Предлагаемый Fix:**

```python
# features/chat/service.py
from core.config import CHAT_DIR

def discard_attachments(items: list[dict]) -> None:
    for item in items:
        name = Path(str(item.get("path") or "")).name
        if name:
            (CHAT_DIR / name).unlink(missing_ok=True)

# features/chat/__init__.py
        try:
            result = reply(message, history, load_products(), config, attachments, tools=ctx.tools)
            ...  # append_chat_turn и сборка result
        except Exception:
            service.discard_attachments(attachments)
            raise
```

---

### [DONE] E-12 🟢 После удаления заказа список клиентов не обновляется молча

- **Файл и строки:** `src/pages/AdminPage.jsx:L849-L850`
- **Тип проблемы:** Пустой catch (`.catch(() => null)`)
- **Фрагмент кода:**

```jsx
                                  const data = await api("/api/admin/clients").catch(() => null);
                                  if (data) setClients(data.clients || []);
```

- **Предлагаемый Fix:**

```jsx
                                  const data = await api("/api/admin/clients").catch((err) => {
                                    setDeskError(`Заказ удалён, но список клиентов не обновился: ${err.message}`);
                                    return null;
                                  });
                                  if (data) setClients(data.clients || []);
```

---

### [DONE] E-13 🟢 Импорт старых JSON может уронить запуск сервера на одном битом поле

- **Файл и строки:** `features/crm/service.py:L479`
- **Тип проблемы:** Нет валидации входных данных (`int()` без защиты)
- **Фрагмент кода:**

```python
                int(raw.get("orders_count") or 0),
```

- **Почему это проблема:** значение вроде `"3 шт"` в старом `clients.json` даёт `ValueError` внутри транзакции `import_legacy`, и сервер не стартует, показывая только стек. Сейчас импорт уже выполнен (отметка в `meta`), но код остаётся опасным для переноса на новую машину с чистой базой.
- **Предлагаемый Fix:**

```python
def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default
...
                _safe_int(raw.get("orders_count")),
```

---

## 4. Пошаговый план исправления (Priority Action Plan)

| # | Файл(ы) | Пункты | Почему в этом порядке |
|---|---------|--------|-----------------------|
| 1 | [DONE] `src/pages/AdminPage.jsx` | S-2, S-4, S-6, S-7, E-7, E-12 | Владелец может решить, что заявок нет, и потерять клиентов. Правки только во фронтенде, риск минимальный. |
| 2 | [DONE] `core/ai/llm.py`, `core/ai/engine.py`, новый `core/ai/health.py`, `core/ai/local.py`, `features/admin_status/__init__.py`, `src/components/ChatWidget.jsx`, `HealthBanner` в `AdminPage.jsx` | S-1, S-3 | Сейчас гости могут неделями получать шаблонные ответы, в том числе неправду про фото, и никто об этом не узнает. |
| 3 | [DONE] `core/router.py`, `server.py` | E-1, E-10 | Без стеков и файла лога остальные проблемы невозможно диагностировать. Это фундамент для пунктов 4–8. |
| 4 | [DONE] `core/db.py` | E-2, S-9 | Молча сломанные бэкапы — это риск безвозвратной потери базы заказов. |
| 5 | [DONE] `core/config.py`, `server.py`, `.env.example` | S-5, S-13 | База может лежать не там, где думает владелец; копии на «OneDrive» могут не попадать в облако; пароль в открытом виде в бэкапах. |
| 6 | [DONE] `core/ai/attachments.py`, `features/chat/__init__.py`, `features/chat/service.py`, `ChatWidget.jsx` | E-3, E-4, E-8, E-11 | Zip-бомба через публичный эндпоинт может уронить процесс; файлы клиентов теряются молча. |
| 7 | [DONE] `core/settings.py`, `features/pdf/__init__.py`, `features/pdf/common.py`, `features/pdf/catalog_pdf.py`, `SELLER_FIELDS` в `AdminPage.jsx` | S-10, S-11, S-15 | Корректность финансовых документов: НДС, Кбе/КНП, дата счёта. |
| 8 | [DONE] `src/components/ShopGrid.jsx` | S-8 | Покупатели видят dev-инструкцию вместо витрины. |
| 9 | [DONE] `src/main.jsx`, `src/App.jsx`, `src/components/ErrorBoundary.jsx`, новый `src/utils/report.js`, эндпоинт `/api/client-errors` | E-5 | Изоляция падений чата и корзины плюс видимость фронтенд-ошибок. |
| 10 | [DONE] `features/catalog/service.py`, `features/catalog/__init__.py` | S-12 | Админ получает «Сохранено» при неверной цене. |
| 11 | [DONE] `core/ai/tools.py` | E-6 | Каталог может пропасть из prompt без следа. |
| 12 | [DONE] `features/crm/__init__.py`, `features/crm/service.py` | E-9, E-13 | Корректность API и устойчивость старта. |
| 13 | [DONE] `src/context/CartContext.jsx` | S-14 | Устаревшие цены в WhatsApp-сообщении мастеру. |
| 14 | [DONE] `src/pages/HomePage.jsx`, `src/data/works.js` | S-16 | Контент: реальные фото вместо заглушек портфолио. |

**Проверка после исправлений (минимальный регресс-чек):**
1. Задать заведомо неверный `AI_API_KEY`, написать в чат. Ожидается: ответ `503` с текстом «Сервис ИИ временно недоступен…» и кнопкой WhatsApp, в шапке чата «ИИ временно недоступен», в кабинете баннер «ИИ не отвечает (http_401…)», в `logs/error.log` строка `[ai.llm] … HTTP 401`.
2. Остановить сервер при открытом кабинете и нажать «Обновить» у заказов. Ожидается: список не стирается, видна ошибка «Нет связи с сервером» и кнопка «Повторить попытку».
3. Отправить в чат текст и файл больше 4 МБ. Ожидается: ответ ИИ плюс отдельное предупреждение о непринятом файле.
4. Указать `MEBEL_DATA_DIR` в `.env` и перезапустить сервер. Ожидается: строка `База: SQLite <новый путь>`.
5. Указать в `BACKUP_MIRROR_DIRS` недоступный диск. Ожидается: ошибка в логе и `mirrors_failed` в `/api/admin/health`.

---

## 5. Статус исправлений

Бэкенд проекта написан на Python (`http.server`), а не на Node.js/Express, поэтому все пункты ТЗ реализованы на Python.

| Модуль ТЗ | Пункты | Что сделано |
|-----------|--------|-------------|
| 1. CRM | S-2, S-4, S-6, S-7, E-7, E-12 | `api()` различает обрыв связи, ответ не в JSON и 401. Загрузка кабинета идёт через `Promise.allSettled`; при сбое виден баннер с кнопкой «Повторить попытку», прежние данные не стираются. Ошибки входа выводятся в видимую область (`role="alert"`). |
| 2. ИИ-чат | S-1, S-3, E-6 | Шаблонный бот `local_reply` удалён. При отказе API или пустом ключе ответ `503` с `code: ai_unavailable / ai_not_configured`. Для фото больше нет фейкового «вижу на изображении». Состояние ИИ хранится в `core/ai/health.py` и выводится в кабинете. |
| 3. Конфигурация | S-5, S-13 | `.env` читается первым при импорте `core/config.py`. Нераскрытый `%OneDrive%` заменяется на `data/mirrors/<папка>` с предупреждением в логе. `PHONE_E164` обязателен: сервер не стартует и `npm run build` падает без него. Номер используется в промпте ИИ, в PDF и на сайте. Заказ с телефоном самой мастерской отклоняется (сервер и формы). |
| 4. Логи и бэкапы | E-1, E-2, E-10, S-9 | `core/logging_setup.py` пишет `logs/server.log` и `logs/error.log` (время, уровень, модуль, полный стек), перехватывает необработанные исключения в основном коде и потоках. Бэкап пишется в `.tmp` и затем переименовывается (`os.replace`); при сбое `.tmp` удаляется, ошибка уходит в лог и в `/api/admin/health`. Повреждённый JSON в БД логируется с контекстом. |
| 5. Zip-бомбы | E-3, E-4, E-8, E-11 | Для `.docx` / `.xlsx` действуют лимиты: не больше 2000 записей, не больше 50 МБ в распакованном виде на архив, коэффициент сжатия не выше 100:1. Чтение идёт потоком и прерывается при превышении. Непринятые файлы показываются клиенту отдельным предупреждением. Файлы удаляются, если ответ ИИ не получен. |
| 6. Счета | S-10, S-11, S-15 | Вшитых «Без НДС» / Кбе 19 / КНП 710 больше нет: эти поля обязательны в реквизитах. Некорректная дата вызывает `InvalidDateError`, повреждённые позиции — `CorruptedOrderError`; в обоих случаях ответ `409`, документ не формируется. Битое фото в каталоге PDF логируется и подписывается «фото недоступно». |
| Прочее | S-8, S-12, S-14, S-16, E-5, E-9, E-13 | Витрина: сообщение об ошибке и кнопка повтора. Каталог: строгая валидация полей (`400`). Корзина: предупреждение, если сверка с каталогом не удалась. Портфолио: показываются только работы с реальным фото (`src/data/works.js`). На фронтенде отдельные Error Boundary для страницы, корзины, чата и кабинета; обработчики `window.onerror` и `unhandledrejection` отправляют отчёты в `/api/client-errors`. `PATCH` заказа без статуса работает. Импорт CRM устойчив к битым полям. |
