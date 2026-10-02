import { useEffect, useState } from "react";

export function SafeImg({ src, fallback = null, ...props }) {
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [src]);

  if (!src || failed) return fallback;
  return <img src={src} onError={() => setFailed(true)} {...props} />;
}

export function PhotoPlaceholder() {
  return (
    <span className="photo-ph" aria-hidden="true">
      <img src="/assets/logo.png" alt="" />
      <span>Фото скоро появится</span>
    </span>
  );
}
