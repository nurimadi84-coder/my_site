import { isShopPhone, isValidPhone } from "../utils/phone";

export function LeadModal({ open, preset, error, busy, onClose, onSubmit, onErrorClear }) {
  if (!open) return null;

  const handleSubmit = (event) => {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const name = String(form.elements.namedItem("name").value || "").trim();
    const phone = String(form.elements.namedItem("phone").value || "").trim();
    const nameOk = name.length > 1;
    const phoneOk = isValidPhone(phone);
    form.elements.namedItem("name").classList.toggle("is-invalid", !nameOk);
    form.elements.namedItem("phone").classList.toggle("is-invalid", !phoneOk);
    if (!nameOk || !phoneOk) {
      onErrorClear?.();
      const errNode = form.querySelector(".lead-modal__error");
      if (errNode) {
        errNode.textContent = !nameOk
          ? "Напишите имя и телефон — так мастер поймёт, кому отвечать."
          : isShopPhone(phone)
            ? "Это номер мастерской. Укажите свой телефон, чтобы мастер мог перезвонить."
            : "Укажите телефон в формате +7 XXX XXX-XX-XX.";
      }
      (nameOk ? form.elements.namedItem("phone") : form.elements.namedItem("name")).focus();
      return;
    }
    onSubmit({ name, phone });
  };

  return (
    <div
      className="lead-modal"
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <div className="lead-modal__panel" role="dialog" aria-modal="true" aria-labelledby="lead-modal-title">
        <div className="lead-modal__head">
          <div>
            <p className="lead-modal__kicker">Заявка</p>
            <h2 id="lead-modal-title">Оформление заказа</h2>
          </div>
          <button className="lead-modal__close" type="button" aria-label="Закрыть" onClick={onClose} disabled={busy}>
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path
                d="M3.5 3.5 12.5 12.5M12.5 3.5 3.5 12.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </div>
        <p className="lead-modal__lead">
          Оставьте имя и телефон — сохраним заявку и откроем WhatsApp с готовым текстом.
        </p>
        <form className="lead-modal__form" id="lead-modal-form" noValidate onSubmit={handleSubmit}>
          <label className="lead-modal__field">
            <span>Имя</span>
            <input
              type="text"
              name="name"
              autoComplete="name"
              required
              maxLength={80}
              placeholder="Как к вам обращаться"
              defaultValue={preset?.name || ""}
              key={`name-${preset?.name || ""}-${open}`}
            />
          </label>
          <label className="lead-modal__field">
            <span>Телефон</span>
            <input
              type="tel"
              name="phone"
              autoComplete="tel"
              required
              maxLength={30}
              placeholder="+7"
              defaultValue={preset?.phone || ""}
              key={`phone-${preset?.phone || ""}-${open}`}
            />
          </label>
          <p className="lead-modal__error" role="status">
            {error}
          </p>
          <button className="btn btn--bronze btn--full" type="submit" disabled={busy}>
            Продолжить в WhatsApp
          </button>
        </form>
      </div>
    </div>
  );
}
