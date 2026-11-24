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

/** Keep an exiting surface until its own transition has settled. */
export function useExit(
  ref: RefObject<HTMLElement>,
  exiting: boolean,
  onExited: () => void,
) {
  const done = useLatest(onExited);
  useLayoutEffect(() => {
    if (!exiting) return;
    let current = true;
    const animations = ref.current?.getAnimations() ?? [];
    Promise.allSettled(animations.map((animation) => animation.finished)).then(() => {
      if (current) done.current();
    });
    return () => { current = false; };
  }, [ref, exiting, done]);
}
