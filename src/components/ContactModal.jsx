import { SITE } from "../site";

export function ContactModal({ open, onClose }) {
  if (!open) return null;

  return (
    <div
      className="contact-modal"
      id="header-contact-pop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="contact-modal__panel" role="dialog" aria-modal="true" aria-labelledby="contact-modal-title">
        <div className="contact-modal__head">
          <div>
            <p className="contact-modal__kicker">Контакты</p>
            <h2 id="contact-modal-title">Связаться с ателье</h2>
          </div>
          <button className="contact-modal__close" type="button" onClick={onClose} aria-label="Закрыть">
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
        <p className="contact-modal__lead">Алматы · выезд по городу. Выберите удобный способ.</p>
        <a className="contact-modal__link" href={`tel:+${SITE.phoneE164}`}>
          <span>Позвонить</span>
          <strong>{SITE.phoneDisplay}</strong>
        </a>
        <a
          className="contact-modal__link"
          href={`https://wa.me/${SITE.phoneE164}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          <span>WhatsApp</span>
          <strong>Написать мастеру</strong>
        </a>
        <a className="contact-modal__link" href={SITE.instagram} target="_blank" rel="noopener noreferrer">
          <span>Instagram</span>
          <strong>{SITE.handle}</strong>
        </a>
      </div>
    </div>
  );
}
