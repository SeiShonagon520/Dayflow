/*
 * 动效强度控制
 *
 * 系统级 prefers-reduced-motion 只是兜底。规范还要求界面里
 * 有一个能调的入口 —— 有人只是嫌动效晃眼，并没有在系统里
 * 关闭动画，让ta每次都要去系统设置里翻是找不到的。
 *
 * 三档：跟随系统 / 减少 / 完整。写入 data-motion 到 <html>，
 * CSS 侧用属性选择器降级，不需要 JS 逐个改样式。
 */
import { useEffect, useRef, useState } from "react";
import { FocusRing } from "@/components/FocusRing";

export type MotionLevel = "system" | "reduced" | "full";

const KEY = "dayflow-motion";

function systemPrefersReduced(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function apply(level: MotionLevel) {
  const root = document.documentElement;
  if (level === "system") {
    root.removeAttribute("data-motion");
  } else {
    root.setAttribute("data-motion", level);
  }
}

export function useMotionLevel(): [MotionLevel, (l: MotionLevel) => void] {
  const [level, setLevel] = useState<MotionLevel>(() => {
    if (typeof localStorage === "undefined") return "system";
    const saved = localStorage.getItem(KEY);
    return saved === "reduced" || saved === "full" ? saved : "system";
  });

  useEffect(() => {
    apply(level);
    try {
      if (level === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, level);
    } catch {
      /* 无痕模式下写不进去，不影响使用 */
    }
  }, [level]);

  return [level, setLevel];
}

const OPTIONS: { value: MotionLevel; label: string; hint: string }[] = [
  { value: "system", label: "跟随系统", hint: "按系统的「减少动态效果」设置" },
  { value: "reduced", label: "减少", hint: "关闭位移与缩放，保留状态提示" },
  { value: "full", label: "完整", hint: "始终播放全部过渡动画" },
];

/** 设置页里用：三段切换 */
export function MotionControl() {
  const [level, setLevel] = useMotionLevel();
  const systemOn = systemPrefersReduced();

  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  /* radiogroup 的标准键盘模型：上下左右方向键切换，
     Tab 只进出整个组一次。 */
  const onKeyDown = (e: React.KeyboardEvent) => {
    const dir =
      e.key === "ArrowRight" || e.key === "ArrowDown" ? 1
      : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1
      : 0;
    if (dir === 0) return;
    e.preventDefault();
    const i = OPTIONS.findIndex((o) => o.value === level);
    const next = (i + dir + OPTIONS.length) % OPTIONS.length;
    setLevel(OPTIONS[next].value);
    /* 等重渲染完再对焦，否则旧选项已卸载、新的还没挂上，
       refs.current[next] 是 null，焦点会掉回 body。 */
    requestAnimationFrame(() => refs.current[next]?.focus());
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)" }}>
            界面动效
          </div>
          <div style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", marginTop: 2 }}>
            {OPTIONS.find((o) => o.value === level)?.hint}
            {level === "system" && systemOn && "　当前系统：已开启「减少动态效果」"}
          </div>
        </div>
      </div>

      <div
        role="radiogroup"
        aria-label="界面动效强度"
        onKeyDown={onKeyDown}
        style={{
          display: "inline-flex",
          padding: 2,
          background: "var(--bg-sunken)",
          borderRadius: "var(--radius-md)",
          gap: 2,
          alignSelf: "flex-start",
        }}
      >
        {OPTIONS.map((o, i) => {
          const active = level === o.value;
          return (
            <button
              key={o.value}
              ref={(el) => { refs.current[i] = el; }}
              type="button"
              role="radio"
              aria-checked={active}
              /* radiogroup 里只有选中项能被 Tab 进去 */
              tabIndex={active ? 0 : -1}
              onClick={() => setLevel(o.value)}
              /* 三档之间的分栏里，28px 高的按钮纵向不足，
                 伪元素补到 40px。横向各有 52–76px，扩得开。 */
              className="df-hit-v"
              style={{
                height: 28,
                padding: "0 14px",
                borderRadius: "var(--radius-sm)",
                background: active ? "var(--bg-surface)" : "transparent",
                color: active ? "var(--text-primary)" : "var(--text-tertiary)",
                fontSize: "var(--text-xs)",
                fontWeight: active
                  ? "var(--weight-semibold)"
                  : "var(--weight-normal)",
                boxShadow: active ? "var(--shadow-sm)" : "none",
                border: "none",
                cursor: "pointer",
                position: "relative",
                touchAction: "manipulation",
                transition: `background var(--dur-base) var(--ease-out),
                            color var(--dur-base) var(--ease-out)`,
              }}
            >
              {o.label}
              <FocusRing />
            </button>
          );
        })}
      </div>
    </div>
  );
}
