import { useEffect, useState } from "react";
import { waText } from "../site";

export function Dock() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      const hero = document.querySelector(".hero");
      if (!hero) return;
      const y = window.scrollY || Math.abs(parseInt(document.body.style.top || "0", 10));
      const pastHero = y > hero.offsetHeight * 0.72;
      const nearFooter = window.innerHeight + y > document.documentElement.scrollHeight - 140;
      setVisible(pastHero && !nearFooter);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className={`dock${visible ? " is-visible" : ""}`} aria-label="Быстрые действия">
      <a className="btn btn--ghost btn--dock" href="#calc">
        Расчёт
      </a>
      <a className="btn btn--bronze btn--dock" href={waText()} target="_blank" rel="noopener noreferrer">
        WhatsApp
      </a>
    </div>
  );
}
