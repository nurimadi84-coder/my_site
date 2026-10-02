import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { SITE, waText } from "../site";
import { ContactModal } from "./ContactModal";

const SECTIONS = [
  { id: "services", index: "01", label: "Услуги" },
  { id: "approach", index: "02", label: "Почему мы" },
  { id: "shop", index: "03", label: "Магазин" },
  { id: "works", index: "04", label: "Работы" },
  { id: "steps", index: "05", label: "Этапы" },
  { id: "calc", index: "06", label: "Расчёт" },
  { id: "contacts", index: "06", label: "Контакты" },
];

const NAV = [
  { href: "#services", n: "01", label: "Услуги" },
  { href: "#approach", n: "02", label: "Почему мы" },
  { href: "#shop", n: "03", label: "Магазин" },
  { href: "#works", n: "04", label: "Работы" },
  { href: "#steps", n: "05", label: "Этапы" },
  { href: "#contacts", n: "06", label: "Контакты", contacts: true },
];

export function Header({ variant = "home", cartFab = null }) {
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [now, setNow] = useState({ index: "00", label: "Ателье", id: "" });
  const lockedScrollRef = useRef(0);
  const pipRef = useRef(null);
  const panelRef = useRef(null);
  const burgerRef = useRef(null);
  const isHome = variant === "home" && location.pathname === "/";

  const setMenuOpen = (open) => {
    setNavOpen(open);
    document.body.classList.toggle("nav-open", open);
    if (burgerRef.current) burgerRef.current.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      lockedScrollRef.current = window.scrollY;
      document.body.style.position = "fixed";
      document.body.style.top = `-${lockedScrollRef.current}px`;
      document.body.style.left = "0";
      document.body.style.right = "0";
    } else {
      document.body.style.position = "";
      document.body.style.top = "";
      document.body.style.left = "";
      document.body.style.right = "";
      window.scrollTo(0, lockedScrollRef.current);
    }
  };

  const setContact = (open) => {
    setContactOpen(open);
    document.body.classList.toggle("is-contact-open", open);
  };

  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY || Math.abs(parseInt(document.body.style.top || "0", 10));
      setScrolled(y > 8);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!isHome) return undefined;
    const placePip = (id) => {
      const pip = pipRef.current;
      const panel = panelRef.current;
      if (!pip || !panel || !window.matchMedia("(min-width: 980px)").matches) return;
      const link = [...panel.querySelectorAll("a[href^='#']")].find(
        (node) => node.getAttribute("href") === `#${id}`
      );
      if (!link) {
        pip.style.width = "0px";
        return;
      }
      pip.style.width = `${link.offsetWidth}px`;
      pip.style.transform = `translateX(${link.offsetLeft}px)`;
    };

    const pick = () => {
      if (window.scrollY < 48) {
        setNow({ index: "00", label: "Ателье", id: "" });
        placePip("");
        return;
      }
      let current = "";
      SECTIONS.forEach((section) => {
        const node = document.getElementById(section.id);
        if (node && node.getBoundingClientRect().top <= window.innerHeight * 0.45) {
          current = section.id;
        }
      });
      const item = SECTIONS.find((s) => s.id === current) || { index: "00", label: "Ателье", id: "" };
      setNow({ index: item.index, label: item.label, id: current });
      placePip(current);
    };

    pick();
    window.addEventListener("scroll", pick, { passive: true });
    window.addEventListener("resize", pick);
    return () => {
      window.removeEventListener("scroll", pick);
      window.removeEventListener("resize", pick);
    };
  }, [isHome]);

  useEffect(() => {
    const onKey = (event) => {
      if (event.key !== "Escape") return;
      if (navOpen) setMenuOpen(false);
      if (contactOpen) setContact(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navOpen, contactOpen]);

  useEffect(
    () => () => {
      document.body.classList.remove("nav-open", "is-contact-open");
      document.body.style.position = "";
      document.body.style.top = "";
      document.body.style.left = "";
      document.body.style.right = "";
    },
    []
  );

  if (variant === "catalog") {
    return (
      <header className="catalog-top">
        <Link className="brand" to="/">
          <span className="brand__seal">
            <img src="/assets/logo.png" width="120" height="120" alt="" />
          </span>
          <span className="brand__text">
            <span className="brand__name">Mebel Almaty</span>
            <span className="brand__since">витрина</span>
          </span>
        </Link>
        <div className="catalog-side">
          {cartFab}
          <a
            className="btn btn--bronze"
            href={waText("Здравствуйте! Хочу оформить заказ.")}
            target="_blank"
            rel="noopener noreferrer"
          >
            WhatsApp
          </a>
        </div>
      </header>
    );
  }

  const brandHref = isHome ? "#top" : "/";
  const BrandTag = isHome ? "a" : Link;
  const brandProps = isHome ? { href: brandHref } : { to: "/" };

  return (
    <>
      <header className={`header${scrolled ? " is-scrolled" : ""}`}>
        <input
          className="nav-toggle"
          type="checkbox"
          id="nav-toggle"
          checked={navOpen}
          onChange={(e) => setMenuOpen(e.target.checked)}
        />

        <BrandTag className="brand" {...brandProps}>
          <span className="brand__seal">
            <svg className="brand__ring" viewBox="0 0 52 52" aria-hidden="true">
              <circle cx="26" cy="26" r="24.5" fill="none" stroke="currentColor" strokeWidth="1" />
            </svg>
            <img
              src="/assets/logo.png"
              width="120"
              height="120"
              alt="Логотип Mebel Almaty: кресло и монограмма M"
            />
          </span>
          <span className="brand__text">
            <span className="brand__name">Mebel Almaty</span>
            <span className="brand__since">с 2016</span>
            {isHome && (
              <span className="header__now">
                <span data-now-index>{now.index}</span>
                <span data-now-label>{now.label}</span>
              </span>
            )}
          </span>
        </BrandTag>

        <nav className="panel" id="site-nav" aria-label="Основное меню" ref={panelRef}>
          <p className="panel__mark">Ателье · Алматы</p>
          {NAV.map((item) => {
            const active = isHome && now.id && item.href === `#${now.id}`;
            if (item.contacts) {
              return (
                <a
                  key={item.href}
                  href={item.href}
                  className={active ? "is-active" : undefined}
                  aria-current={active ? "true" : undefined}
                  data-open-contacts
                  onClick={(e) => {
                    e.preventDefault();
                    if (navOpen) setMenuOpen(false);
                    setContact(true);
                  }}
                >
                  <span>{item.n}</span> {item.label}
                </a>
              );
            }
            if (!isHome) {
              return (
                <Link
                  key={item.href}
                  to={{ pathname: "/", hash: item.href }}
                  onClick={() => {
                    if (navOpen) setMenuOpen(false);
                  }}
                >
                  <span>{item.n}</span> {item.label}
                </Link>
              );
            }
            return (
              <a
                key={item.href}
                href={item.href}
                className={active ? "is-active" : undefined}
                aria-current={active ? "true" : undefined}
                onClick={() => {
                  if (navOpen) setMenuOpen(false);
                }}
              >
                <span>{item.n}</span> {item.label}
              </a>
            );
          })}
          <span className="nav-pip" aria-hidden="true" ref={pipRef} />
          <label
            htmlFor="nav-toggle"
            className="panel__close"
            onClick={() => setMenuOpen(false)}
          >
            Закрыть меню
          </label>
        </nav>

        <div className={`header-contact${contactOpen ? " is-open" : ""}`}>
          <button
            className="header__wa"
            type="button"
            id="header-contact-btn"
            aria-expanded={contactOpen}
            aria-controls="header-contact-pop"
            aria-haspopup="dialog"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setContact(!contactOpen);
            }}
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
            <span>{SITE.phoneDisplay}</span>
          </button>
        </div>

        {isHome ? (
          <a className="cta" href="#calc">
            <span className="cta__full">Рассчитать стоимость</span>
            <span className="cta__short">Расчёт</span>
          </a>
        ) : (
          <Link className="cta" to="/#calc">
            <span className="cta__full">Рассчитать стоимость</span>
            <span className="cta__short">Расчёт</span>
          </Link>
        )}

        {cartFab}

        <label className="burger" htmlFor="nav-toggle" ref={burgerRef}>
          <span className="burger__lines" aria-hidden="true" />
          <span className="visually-hidden">Открыть меню</span>
        </label>
      </header>

      <ContactModal open={contactOpen} onClose={() => setContact(false)} />
    </>
  );
}
