/*
 * 对话框
 *
 * 模态的三个硬性条件，缺一个就不是模态：
 *   1. 焦点进来（否则键盘用户还停在背后的页面上）
 *   2. 焦点出不去（Tab 会跑到背后的导航，读屏也会开始念背景）
 *   3. 关闭后焦点回到触发它的那个按钮
 *
 * 实测修复前的情况：焦点进了对话框，但连按 25 次 Tab
 * 焦点就跑到了背后的 Dayflow 侧栏 —— 背景既没 inert，
 * 也没有任何循环逻辑。
 *
 * 用 portal 把面板挂到 body 上，然后给 .df-shell 加 inert：
 * 对话框本身在 .df-main 内部，不 portal 就没法把背景单独关掉。
 */
import { ReactNode, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useExit, useSurfaceEnter } from "@/lib/motion";
import { useLatest } from "@/lib/useLatest";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type=hidden])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function focusablesIn(root: HTMLElement | null): HTMLElement[] {
  if (!root) return [];
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE))
    .filter((el) => el.offsetWidth > 0 || el.offsetHeight > 0);
}

export function Dialog({
  open,
  onClose,
  onExited,
  labelledBy,
  size = "md",
  flush = false,
  children,
}: {
  open: boolean;
  onClose: () => void;
  onExited: () => void;
  labelledBy?: string;
  size?: "md" | "lg";
  flush?: boolean;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  /** 打开时记住焦点在哪，关掉还回去 */
  const restoreTo = useRef<HTMLElement | null>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const closing = !open;
  const closingRef = useLatest(closing);
  useSurfaceEnter(overlay);
  useExit(overlay, closing, onExited);
  const onCloseRef = useLatest(onClose);

  useEffect(() => {
    restoreTo.current = document.activeElement as HTMLElement | null;

    // 背景 inert：不能 Tab 进去，也不能被点。
    // 用 inert 而不是 aria-hidden —— 后者只藏内容不挡交互。
    const shell = document.querySelector(".df-shell");
    shell?.setAttribute("inert", "");

    const items = focusablesIn(panel.current);
    (items[0] ?? panel.current)?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (closingRef.current) {
        if (!((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k")) {
          e.preventDefault();
          e.stopPropagation();
        }
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;

      /* 循环：到底部跳回顶部，到顶部跳回底部。
         键盘用户能 Tab 走出模态，是它最严重的失败 ——
         他会以为自己在操作背后的页面。 */
      const list = focusablesIn(panel.current);
      if (list.length === 0) {
        e.preventDefault();
        panel.current?.focus();
        return;
      }
      const firstItem = list[0];
      const lastItem = list[list.length - 1];
      const active = document.activeElement;

      if (e.shiftKey &&
          (active === firstItem || !panel.current?.contains(active))) {
        e.preventDefault();
        lastItem.focus();
      } else if (!e.shiftKey && active === lastItem) {
        e.preventDefault();
        firstItem.focus();
      }
    };

    document.addEventListener("keydown", onKey, true);

    return () => {
      document.removeEventListener("keydown", onKey, true);
      shell?.removeAttribute("inert");
      // 焦点还回去 —— 停在 body 上等于把用户丢回起点
      restoreTo.current?.focus?.();
    };
  }, [closingRef, onCloseRef]);

  return createPortal(
    <div
      ref={overlay}
      className="df-overlay"
      data-closing={closing || undefined}
      onClick={closing ? undefined : onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--scrim)",
        display: "flex",
        alignItems: flush ? "flex-start" : "center",
        justifyContent: "center",
        padding: flush ? "min(14vh, 96px) var(--space-4) var(--space-4)" : "var(--space-4)",
        zIndex: "var(--z-modal)",
      }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        /* 面板本身要能接收焦点：里面一个可聚焦元素都没有时，
           焦点会掉回 body，键盘用户直接失联。 */
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className="df-dialog"
        data-size={size}
        data-flush={flush ? "true" : undefined}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}

export function DialogHeader({
  title,
  description,
  id,
}: {
  title: ReactNode;
  description?: ReactNode;
  id?: string;
}) {
  return (
    <div className="df-dialog-head">
      <h3 id={id} className="df-dialog-title">{title}</h3>
      {description && <p className="df-dialog-desc">{description}</p>}
    </div>
  );
}

export function DialogBody({ children }: { children: ReactNode }) {
  return <div className="df-dialog-body">{children}</div>;
}

export function DialogFooter({ children }: { children: ReactNode }) {
  return <div className="df-dialog-foot">{children}</div>;
}
