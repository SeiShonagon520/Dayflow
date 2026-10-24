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
  labelledBy,
  children,
}: {
  open: boolean;
  onClose: () => void;
  labelledBy?: string;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  /** 打开时记住焦点在哪，关掉还回去 */
  const restoreTo = useRef<HTMLElement | null>(null);
  /* 退场状态由外部驱动 —— 父组件在退场结束后才卸载本组件。
     自己管一个 150ms 计时器会和父组件的那个抢跑：
     实测遮罩在 12ms 就被移除，退场动画一帧都没播。
     所以这里不计时，只根据 open 判断该播入场还是退场。 */
  const closing = !open;
  /* 回调存进 ref：它每次 render 都换身份，但它变了不该导致
     重新抓一遍「打开时焦点在哪」+ 重新 focus 第一个字段。
     之前这个 effect 依赖 [open, onClose]，父组件任何一次重渲染
     （比如删除后那条 6 秒 toast 计时器到期）都会把它重跑一遍 ——
     实测：焦点从正在输入的 textarea 被抢回第一个 input。 */
  const onCloseRef = useLatest(onClose);

  useEffect(() => {
    if (!open) return;

    restoreTo.current = document.activeElement as HTMLElement | null;

    // 背景 inert：不能 Tab 进去，也不能被点。
    // 用 inert 而不是 aria-hidden —— 后者只藏内容不挡交互。
    const shell = document.querySelector(".df-shell");
    shell?.setAttribute("inert", "");

    const items = focusablesIn(panel.current);
    (items[0] ?? panel.current)?.focus();

    const onKey = (e: KeyboardEvent) => {
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
    /* 只依赖 open。加上 onClose 会让父组件每次重渲染都重跑这个
       effect —— 实测焦点会从正在输入的 textarea 跳回第一个 input。
       最新的那个 onClose 通过 onCloseRef 拿，不需要靠依赖触发。 */
  }, [open]);

  /* 退场期间组件保持挂载，由父组件在退场结束后卸载。
     提前 return null 就等于没有退场。 */
  return createPortal(
    <div
      className={`df-overlay ${closing ? "df-overlay-out" : ""}`}
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--scrim)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-4)",
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
        /* 入场和退场是两组互斥的 class ——
           同时挂会互相覆盖，退场根本播不出来。 */
        className={`df-dialog ${closing ? "df-fade-out" : "df-pop-in"}`}
        style={{
          background: "var(--bg-raised)",
          border: "1px solid var(--border-default)",
          borderRadius: "var(--radius-xl)",
          boxShadow: "var(--shadow-lg)",
          padding: "var(--space-6)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-4)",
        }}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
