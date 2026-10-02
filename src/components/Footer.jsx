import { Link } from "react-router-dom";
import { SITE, waText } from "../site";

export function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="footer" id="contacts">
      <div className="wrap footer__grid">
        <div>
          <a className="brand brand--footer" href="#top">
            <span className="brand__seal">
              <img src="/assets/logo.png" width="120" height="120" alt="" />
            </span>
            <span className="brand__text">
              <span className="brand__name">Mebel Almaty</span>
              <span className="brand__since">корпусная мебель</span>
            </span>
          </a>
          <p className="footer__about">
            Шкафы, кровати и кухни на заказ в Алматы. От замера до монтажа — с 2016 года.
          </p>
        </div>

        <nav aria-label="Разделы">
          <p className="footer__label">Разделы</p>
          <a href="#services">Услуги</a>
          <a href="#approach">Почему мы</a>
          <a href="#shop">Магазин</a>
          <Link to="/products">Все товары</Link>
          <a href="#works">Работы</a>
          <a href="#steps">Этапы</a>
          <a href="#calc">Рассчитать стоимость</a>
        </nav>

        <div>
          <p className="footer__label">Контакты</p>
          <a href={SITE.instagram} target="_blank" rel="noopener noreferrer">
            {SITE.handle}
          </a>
          <a href={`tel:+${SITE.phoneE164}`}>{SITE.phoneDisplay}</a>
          <a href={waText()} target="_blank" rel="noopener noreferrer">
            WhatsApp
          </a>
          <p className="footer__city">г. Алматы · выезд по городу и области</p>
        </div>
      </div>

      <div className="wrap footer__bar">
        <p>
          © 2016–{year} Mebel Almaty
        </p>
        <Link to="/admin">Кабинет</Link>
        <a href="#top">Наверх</a>
      </div>

      <svg className="footer-ornament" aria-hidden="true" focusable="false">
        <defs>
          <pattern id="horn-edge" width="88" height="36" patternUnits="userSpaceOnUse">
            <path
              d="M44 28c-8 0-14-4.4-16-11-1.5-5 1.6-9 6.4-8.2 3.8.6 6 4 4.6 7.4-1.2 3-4 4.5-7 3.6"
              fill="none"
              stroke="#C4A36A"
              strokeWidth="1"
              strokeLinecap="round"
            />
            <path
              d="M44 28c8 0 14-4.4 16-11 1.5-5-1.6-9-6.4-8.2-3.8.6-6 4-4.6 7.4 1.2 3 4 4.5 7 3.6"
              fill="none"
              stroke="#C4A36A"
              strokeWidth="1"
              strokeLinecap="round"
            />
            <path d="M44 25.2 45.6 26.8 44 28.4 42.4 26.8 44 25.2z" fill="#C4A36A" />
          </pattern>
        </defs>
        <rect width="100%" height="36" fill="url(#horn-edge)" />
      </svg>
    </footer>
  );
}
