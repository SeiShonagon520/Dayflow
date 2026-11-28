import { RefObject, useLayoutEffect } from "react";
import { useLatest } from "./useLatest";

export type MotionLevel = "system" | "reduced" | "full";
const key = "dayflow-motion";

export function readMotionLevel(): MotionLevel {
  try {
    const saved = localStorage.getItem(key);
    if (saved === "reduced" || saved === "full") return saved;
  } catch {
    // Storage can be unavailable in a restricted webview.
  }
  return "system";
}

export function isReducedMotionActive(): boolean {
  if (typeof document === "undefined") return false;
  const level = document.documentElement.dataset.motion;
  if (level === "reduced") return true;
  if (level === "full") return false;
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

export function applyMotionLevel(level: MotionLevel) {
  if (level === "system") document.documentElement.removeAttribute("data-motion");
  else document.documentElement.dataset.motion = level;
}

export function saveMotionLevel(level: MotionLevel) {
  applyMotionLevel(level);
  try {
    localStorage.setItem(key, level);
  } catch {
    // The current window still honors the selected preference.
  }
}

export function restorePreviousMotion(value: string) {
  try {
    if (localStorage.getItem(key) !== null) return;
    if (value === "off") saveMotionLevel("reduced");
    else if (value === "on") saveMotionLevel("full");
  } catch {
    // Storage may be unavailable in a restricted webview.
  }
}

/** Commit the initial styles once so transitions work on older WebView2 runtimes. */
export function useSurfaceEnter(ref: RefObject<HTMLElement>) {
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    void getComputedStyle(element).opacity;
    element.dataset.entered = "";
    return () => { delete element.dataset.entered; };
  }, [ref]);
}

export function pendingMotion(element: HTMLElement | null | undefined) {
  if (isReducedMotionActive() || !element?.getAnimations) return;
  const animations = element.getAnimations().filter((animation) => animation.playState === "running" || animation.pending);
  if (animations.length) {
    return Promise.allSettled(animations.map((animation) => animation.finished));
  }
}

/**
 * Keep an exiting surface mounted until its own CSS transition/animation settles.
 * In reduced-motion mode (or when no animations are running), completes immediately
 * so there is zero artificial delay.
 */
export function useExit(
  ref: RefObject<HTMLElement>,
  exiting: boolean,
  onExited: () => void,
) {
  const done = useLatest(onExited);
  useLayoutEffect(() => {
    if (!exiting) return;
    const motion = pendingMotion(ref.current);
    if (!motion) {
      done.current();
      return;
    }
    let current = true;
    motion.then(() => {
      if (current) done.current();
    });
    return () => { current = false; };
  }, [ref, exiting, done]);
}
