import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { SITE, waText } from "../site";
import { isShopPhone, isValidPhone } from "../utils/phone";
import { useReveal } from "../hooks/useReveal";
import { useCrm } from "../context/CrmContext";
import { Header } from "../components/Header";
import { Footer } from "../components/Footer";
import { Dock } from "../components/Dock";
import { ShopGrid } from "../components/ShopGrid";
import { CartFab } from "../components/Cart";
import { PUBLISHED_WORKS } from "../data/works";

export function HomePage() {
  const mainRef = useRef(null);
  const { openWhatsApp } = useCrm();
  const [progress, setProgress] = useState(0);
  const [formError, setFormError] = useState("");
  useReveal(mainRef);

  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY || Math.abs(parseInt(document.body.style.top || "0", 10));
      const height = document.documentElement.scrollHeight - window.innerHeight;
      const ratio = height > 0 ? Math.min(1, y / height) : 0;
      setProgress(ratio);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const handleCalc = async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const name = form.elements.namedItem("name");
    const phone = form.elements.namedItem("phone");
    const kind = form.elements.namedItem("kind");
    const note = form.elements.namedItem("note");

    const nameOk = name.value.trim().length > 1;
    const phoneOk = isValidPhone(phone.value);

    name.closest(".field")?.classList.toggle("is-invalid", !nameOk);
    phone.closest(".field")?.classList.toggle("is-invalid", !phoneOk);

    if (!nameOk || !phoneOk) {
      setFormError(
        !nameOk
          ? "Напишите имя и телефон — так мы поймём, кому отвечать."
          : isShopPhone(phone.value)
            ? "Это номер мастерской. Укажите свой телефон, чтобы мастер мог перезвонить."
            : "Укажите телефон в формате +7 XXX XXX-XX-XX."
      );
      (nameOk ? phone : name).focus();
      return;
    }

    setFormError("");
    const lines = [
      "Здравствуйте! Оформляю заказ на корпусную мебель.",
      "",
      `Имя: ${name.value.trim()}`,
      `Телефон: ${phone.value.trim()}`,
      `Изделие: ${kind.value}`,
    ];
    if (note.value.trim()) lines.push(`Комментарий: ${note.value.trim()}`);
    lines.push("", "Жду подтверждение и расчёт.");
    const text = lines.join("\n");
    const url = waText(text);
    await openWhatsApp(url, {
      source: "calc",
      customer: { name: name.value.trim(), phone: phone.value.trim() },
      items: [{ title: kind.value, qty: 1, kind: "Заявка" }],
      note: note.value.trim(),
      message: text,
    });
  };

  return (
    <>
      <div className="progress" aria-hidden="true" style={{ transform: `scaleX(${progress})` }} />
      <Header variant="home" cartFab={<CartFab />} />

      <main id="top" ref={mainRef}>
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero__cage" aria-hidden="true">
            <svg viewBox="0 0 480 560" fill="none">
              <circle cx="250" cy="250" r="188" stroke="currentColor" strokeWidth="0.7" />
              <ellipse cx="250" cy="250" rx="78" ry="188" stroke="currentColor" strokeWidth="0.7" />
              <ellipse cx="250" cy="250" rx="132" ry="188" stroke="currentColor" strokeWidth="0.7" />
              <ellipse cx="250" cy="250" rx="188" ry="86" stroke="currentColor" strokeWidth="0.7" />
              <ellipse cx="250" cy="250" rx="188" ry="142" stroke="currentColor" strokeWidth="0.55" />
              <g transform="translate(178 214) scale(2)">
                <use href="#horn" />
              </g>
            </svg>
          </div>

          <div className="hero__copy">
            <p className="eyebrow">Корпусная мебель · Алматы</p>
            <h1 id="hero-title" className="hero__title">
              Корпусная мебель,
              <br />
              <em>которая чувствует</em>
              <br />
              ваше пространство
            </h1>
            <p className="hero__lead">
              Индивидуальные шкафы, кровати и кухни. С 2016 года проектируем и производим под конкретную комнату — от замера до монтажа, одной мастерской.
            </p>
            <div className="hero__actions">
              <a className="btn btn--ghost" href="#works">
                Смотреть работы
              </a>
              <a
                className="btn btn--bronze"
                href={waText()}
                target="_blank"
                rel="noopener noreferrer"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true" className="btn__icon">
                  <path
                    d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v7A2.5 2.5 0 0 1 16.5 16H9l-4 3.2V6.5z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.4"
                    strokeLinejoin="round"
                  />
                </svg>
                Связаться в WhatsApp
              </a>
            </div>
            <p className="hero__meta">
              <a href={SITE.instagram} target="_blank" rel="noopener noreferrer">
                {SITE.handle}
              </a>
              <span>выезд по городу</span>
              <span>сборка под ключ</span>
            </p>
          </div>

          <figure className="hero__frame">
            <svg className="hero__sketch" viewBox="0 0 640 800" fill="none" aria-hidden="true">
              <path d="M64 620 H576" stroke="currentColor" strokeWidth="0.8" />
              <path d="M96 620 V168 H472 V620" stroke="currentColor" strokeWidth="0.8" />
              <path d="M318 168 V620" stroke="currentColor" strokeWidth="0.6" />
              <path d="M140 248 H268" stroke="currentColor" strokeWidth="0.6" />
              <path d="M140 332 H268" stroke="currentColor" strokeWidth="0.6" />
              <rect x="346" y="392" width="92" height="228" stroke="currentColor" strokeWidth="0.7" />
              <path d="M368 430 H416 M368 454 H416" stroke="currentColor" strokeWidth="0.55" />
              <path d="M508 430 C548 430 564 468 564 520 C564 572 540 596 508 596" stroke="currentColor" strokeWidth="0.7" />
            </svg>
            <span className="brackets" aria-hidden="true" />
            <figcaption className="plaque">
              <span>Интерьерный кадр</span>
              <strong>Алматы · с 2016</strong>
            </figcaption>
          </figure>
        </section>

        <section className="sec" id="services" aria-labelledby="services-title">
          <div className="wrap">
            <header className="sec-head reveal">
              <p className="kicker">01 — Услуги</p>
              <div className="sec-head__row">
                <h2 id="services-title">
                  Три дисциплины.
                  <br />
                  Одна мастерская.
                </h2>
                <p className="dek">
                  Шкаф, кровать и кухня считаются от вашей стены, света и того, как вы живёте. Не из чужого каталога.
                </p>
              </div>
            </header>

            <div className="bento">
              <article className="tile tile--wardrobe reveal">
                <div className="tile__top">
                  <svg className="tile__icon" viewBox="0 0 32 32" aria-hidden="true">
                    <rect x="6.5" y="4.5" width="19" height="23" rx="0.5" fill="none" stroke="currentColor" strokeWidth="1.2" />
                    <path d="M16 4.5 v23" fill="none" stroke="currentColor" strokeWidth="1.2" />
                    <path d="M16 16.2 h3.2 c1.4 0 2.3.8 2.3 1.9 0 1.3-1 1.9-2.2 1.5" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                  </svg>
                  <span className="tile__k">Шкафы</span>
                </div>
                <h3>Индивидуальные шкафы</h3>
                <p>
                  В нишу, от стены до стены, гардеробная с островом. Наполнение — под пальто, обувь, бельё и чемоданы. Учитываем розетки, короба вентиляции и сторону, куда открывается дверь.
                </p>
              </article>

              <article className="tile tile--bed reveal">
                <div className="tile__top">
                  <svg className="tile__icon" viewBox="0 0 32 32" aria-hidden="true">
                    <path d="M5 20.5 V13 c0-3.2 2.8-5.5 6.5-5.5 h9 c3.7 0 6.5 2.3 6.5 5.5 v7.5" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                    <path d="M4.5 20.5 h23 M6.5 20.5 v4.5 M25.5 20.5 v4.5" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                  </svg>
                  <span className="tile__k">Спальня</span>
                </div>
                <h3>Дизайнерские кровати</h3>
                <p>
                  Каркас, изголовье и хранение как одна вещь. Высота под ваш матрас, глубина ниш, ткань, которая не спорит с остальной спальней.
                </p>
              </article>

              <article className="tile tile--kitchen reveal">
                <div className="tile__top">
                  <svg className="tile__icon" viewBox="0 0 32 32" aria-hidden="true">
                    <path d="M4.5 14.5 h23 v11 h-23 z" fill="none" stroke="currentColor" strokeWidth="1.2" />
                    <path d="M4.5 20 h23 M12 14.5 V8.2 c0-1.8 1.6-3 3.5-3 h1 c1.9 0 3.5 1.2 3.5 3 v6.3" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                  </svg>
                  <span className="tile__k">Кухни</span>
                </div>
                <h3>Современные кухни</h3>
                <p>
                  Рабочие зоны без визуального шума. Фасады матовые или в шпоне, ящики с доводчиками, техника в нишах. Раскрой — только после 3D и сметы.
                </p>
              </article>

              <aside className="tile tile--note reveal">
                <svg className="tile__horn" aria-hidden="true">
                  <use href="#horn" />
                </svg>
                <p>Берём комнату целиком. Если шкаф, кровать и свет спорят друг с другом — проект ещё не готов.</p>
                <p className="tile__materials">
                  ЛДСП и МДФ · шпон · эмаль · кромка в тон · фурнитура с доводчиком · текстиль изголовья
                </p>
              </aside>
            </div>
          </div>
        </section>

        <section className="sec sec--approach" id="approach" aria-labelledby="approach-title">
          <div className="watermark" aria-hidden="true">
            <svg viewBox="0 0 72 32">
              <use href="#horn" />
            </svg>
          </div>
          <div className="wrap">
            <header className="sec-head reveal">
              <p className="kicker">02 — Почему мы</p>
              <div className="sec-head__row">
                <h2 id="approach-title">Мебель судят по стыкам, а не по рендеру.</h2>
                <p className="dek">Много воздуха в проекте — и на стене тоже. Ниже то, на чём держится мастерская с 2016 года.</p>
              </div>
            </header>

            <ol className="reasons">
              {[
                ["01", "Опыт с 2016 года", "Десять лет одной мастерской в Алматы. Видели, как мебель живёт в новостройках с неровными стенами и в домах, где зимой воздух суше, чем кажется по проекту."],
                ["02", "Премиальные материалы", "Влагостойкие плиты там, где есть пар и вода. Кромка в цвет фасада. Петли и направляющие с доводчиками — чтобы шкаф не стучал на второй год."],
                ["03", "Точность до миллиметра", "Раскрой после замера, а не по плану застройщика. Зазоры, цоколь и примыкание к потолку подгоняем на монтаже, когда стена «гуляет»."],
                ["04", "Сборка под ключ", "Привозим, собираем, регулируем фасады, увозим упаковку. Вы принимаете комнату, а не набор коробок и инструкцию."],
              ].map(([n, title, text]) => (
                <li className="reason reveal" key={n}>
                  <span className="reason__n">{n}</span>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </li>
              ))}
            </ol>

            <blockquote className="pull reveal">
              <p>Сначала стены, потом фасады. Мебель, которая спорит с комнатой, быстро устаревает.</p>
              <footer>Мастерская · Алматы</footer>
            </blockquote>
          </div>
        </section>

        <section className="sec" id="shop" aria-labelledby="shop-title">
          <div className="wrap">
            <header className="sec-head reveal">
              <p className="kicker">03 — Магазин</p>
              <div className="sec-head__row">
                <h2 id="shop-title">Готовые изделия.</h2>
                <p className="dek">
                  Можно забрать как есть или повторить в другом размере и цвете. Карточки добавляются в кабинете — на сайте они появляются сразу.
                </p>
              </div>
            </header>
            <ShopGrid limit={3} />
            <p className="shop-more">
              <Link className="btn btn--line" to="/products">
                Все товары
              </Link>
            </p>
          </div>
        </section>

        <div className="rule wrap" aria-hidden="true">
          <i />
          <svg viewBox="0 0 72 32" width="72" height="28">
            <use href="#horn" />
          </svg>
          <i />
        </div>

        <section className="sec sec--works" id="works" aria-labelledby="works-title">
          <div className="wrap">
            <header className="sec-head reveal">
              <p className="kicker">04 — Портфолио</p>
              <div className="sec-head__row">
                <h2 id="works-title">Гардеробные, кухни, спальни.</h2>
                <p className="dek">
                  Не витринные комплекты — вещи под конкретные стены. Живые кадры готовых комнат смотрите в ленте Instagram.
                </p>
              </div>
            </header>

            {PUBLISHED_WORKS.length ? (
              <div className="feed">
                {PUBLISHED_WORKS.map((item) => (
                  <figure className={`${item.cls} reveal`} key={item.idx}>
                    <div className="shot__frame">
                      <img src={item.photo} alt={`${item.title}: ${item.sub}`} loading="lazy" />
                      <span className="brackets" aria-hidden="true" />
                      <span className="shot__idx">{item.idx}</span>
                    </div>
                    <figcaption>
                      <strong>{item.title}</strong>
                      <span>{item.sub}</span>
                    </figcaption>
                  </figure>
                ))}
              </div>
            ) : null}

            <p className="works-cta reveal">
              <a className="btn btn--line" href={SITE.instagram} target="_blank" rel="noopener noreferrer">
                Больше работ в нашем Instagram
                <span>{SITE.handle}</span>
              </a>
            </p>
          </div>
        </section>

        <section className="sec" id="steps" aria-labelledby="steps-title">
          <div className="wrap">
            <header className="sec-head reveal">
              <p className="kicker">05 — Этапы</p>
              <div className="sec-head__row">
                <h2 id="steps-title">От замера до чистой комнаты.</h2>
                <p className="dek">
                  Четыре шага. Срок и состав работ фиксируем в смете до запуска в цех — без «потом уточним».
                </p>
              </div>
            </header>

            <div className="steps-layout">
              <ol className="steps">
                {[
                  ["01", "1 визит", "Замер", "Приезжаем по Алматы, снимаем размеры с учётом кривизны стен, труб, подоконников и того, куда открываются двери. План застройщика не заменяет замер."],
                  ["02", "2–4 дня", "3D-проект", "Показываем мебель в вашей комнате: фасады, ручки или их отсутствие, цвет кромки, внутреннее наполнение. Смету прикладываем к проекту, а не вместо него."],
                  ["03", "14–25 дней", "Производство", "Раскрой, кромление, присадка, сборка корпуса в цехе. Кухня со сложным камнем — дольше, шкаф в нишу — часто быстрее. Срок называем до старта."],
                  ["04", "1 день", "Доставка и монтаж", "Привозим, заносим, собираем, регулируем фасады и ящики, увозим упаковку. Если стена ведёт себя не по плану — подгоняем на месте, а не оставляем щель."],
                ].map(([n, mark, title, text]) => (
                  <li className="step reveal" key={n}>
                    <span className="step__mark" aria-hidden="true">
                      <svg viewBox="0 0 24 24">
                        <use href="#horn" />
                      </svg>
                    </span>
                    <div>
                      <p className="step__k">
                        <span>{n}</span> {mark}
                      </p>
                      <h3>{title}</h3>
                      <p>{text}</p>
                    </div>
                  </li>
                ))}
              </ol>

              <aside className="steps-aside reveal">
                <p className="kicker">Обычный срок</p>
                <p className="steps-aside__big">
                  14–25<span>дней</span>
                </p>
                <p>
                  На изготовление заказа средней сложности. Точную дату ставим после 3D и выбора материала — когда уже ясно, что именно идёт в раскрой.
                </p>
              </aside>
            </div>
          </div>
        </section>

        <section className="calc" id="calc" aria-labelledby="calc-title">
          <div className="wrap calc__grid">
            <div className="reveal">
              <p className="kicker kicker--light">Заявка</p>
              <h2 id="calc-title">Расскажите о комнате — посчитаем по делу.</h2>
              <p className="calc__lead">
                Без витринных цен «от». Назовите задачу: шкаф, кровать или кухня. Ответим в WhatsApp, что реально сделать и в каком порядке.
              </p>
              <ul className="calc__points">
                <li>Выезд замерщика по Алматы</li>
                <li>3D до запуска в цех</li>
                <li>Смета с материалами и фурнитурой</li>
              </ul>
            </div>

            <form className="calc__form reveal" noValidate onSubmit={handleCalc}>
              <label className="field">
                <span>Имя</span>
                <input type="text" name="name" autoComplete="name" placeholder="Как к вам обращаться" required />
              </label>
              <label className="field">
                <span>Телефон</span>
                <input type="tel" name="phone" autoComplete="tel" inputMode="tel" placeholder="+7" required />
              </label>
              <label className="field">
                <span>Что изготавливаем</span>
                <select name="kind" defaultValue="Шкаф или гардеробная">
                  <option>Шкаф или гардеробная</option>
                  <option>Кровать</option>
                  <option>Кухня</option>
                  <option>Несколько предметов</option>
                  <option>Пока не решил(а)</option>
                </select>
              </label>
              <label className="field">
                <span>Комментарий</span>
                <textarea name="note" rows={3} placeholder="Район, примерные размеры, срок" />
              </label>
              <p className="form-error" role="status">
                {formError}
              </p>
              <button className="btn btn--bronze btn--full" type="submit">
                Отправить в WhatsApp
              </button>
              <p className="form-note">Откроется чат с готовым текстом. Имя и телефон сохраним в заявке, чтобы быстро ответить.</p>
            </form>
          </div>
        </section>
      </main>

      <Footer />
      <Dock />
    </>
  );
}
