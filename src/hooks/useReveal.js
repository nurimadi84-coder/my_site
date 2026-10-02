import { useEffect } from "react";

/**
 * Adds .is-in to elements with .reveal when they enter the viewport.
 * Pass a container ref, or omit to observe the whole document.
 */
export function useReveal(containerRef) {
  useEffect(() => {
    const root = containerRef?.current || document;
    const nodes = [...root.querySelectorAll(".reveal:not(.is-in)")];
    if (!nodes.length) return undefined;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      nodes.forEach((node) => node.classList.add("is-in"));
      return undefined;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-in");
          observer.unobserve(entry.target);
        });
      },
      { threshold: 0.16, rootMargin: "0px 0px -8% 0px" }
    );

    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [containerRef]);
}
