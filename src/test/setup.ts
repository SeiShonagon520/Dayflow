import "@testing-library/jest-dom/vitest";

// jsdom does not implement matchMedia or Web Animations API by default.
if (typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

if (typeof HTMLElement !== "undefined" && typeof HTMLElement.prototype.getAnimations !== "function") {
  HTMLElement.prototype.getAnimations = () => [];
}
