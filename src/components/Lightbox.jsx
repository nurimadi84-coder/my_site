import { useEffect } from "react";

export function Lightbox({ images, index, onClose, onStep }) {
  const many = images.length > 1;

  useEffect(() => {
    if (!images.length) return undefined;
    document.body.classList.add("is-lightbox-open");
    const onKey = (event) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowLeft") onStep(-1);
      if (event.key === "ArrowRight") onStep(1);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.classList.remove("is-lightbox-open");
      document.removeEventListener("keydown", onKey);
    };
  }, [images, onClose, onStep]);

  if (!images.length) return null;

  return (
    <div
      className="lightbox"
      id="lightbox"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <button className="lightbox__close" type="button" aria-label="Закрыть фото" onClick={onClose}>
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
      {many ? (
        <button className="lightbox__nav lightbox__nav--prev" type="button" aria-label="Предыдущее фото" onClick={() => onStep(-1)}>
          ‹
        </button>
      ) : null}
      <img className="lightbox__img" id="lightbox-image" src={images[index]} alt="" />
      {many ? (
        <button className="lightbox__nav lightbox__nav--next" type="button" aria-label="Следующее фото" onClick={() => onStep(1)}>
          ›
        </button>
      ) : null}
      {many ? (
        <p className="lightbox__count" id="lightbox-count">
          {index + 1} / {images.length}
        </p>
      ) : null}
    </div>
  );
}
