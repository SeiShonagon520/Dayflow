/*
 * 基础 UI 组件
 *
 * 这些是「所有页面都该用同一套」的东西。目的是消除旧架构里的问题：
 * 那里每个按钮各自 setStyleSheet，改一次样式要翻十几个文件。
 *
 * 全部只用 token，不写死任何色值/像素值。
 */

import { CSSProperties, ReactNode, forwardRef } from "react";

// ── Button ────────────────────────────────────────────────

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  loading?: boolean;
  icon?: ReactNode;
  children?: ReactNode;
  onClick?: () => void;
  title?: string;
  fullWidth?: boolean;
  type?: "button" | "submit";
}

const BTN_HEIGHT: Record<ButtonSize, number> = { sm: 28, md: 34, lg: 42 };
const BTN_PX: Record<ButtonSize, number> = { sm: 10, md: 14, lg: 20 };
const BTN_FS: Record<ButtonSize, string> = {
  sm: "var(--text-xs)",
  md: "var(--text-sm)",
  lg: "var(--text-md)",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "secondary",
      size = "md",
      disabled,
      loading,
      icon,
      children,
      onClick,
      title,
      fullWidth,
      type = "button",
    },
    ref
  ) {
    const palette: Record<ButtonVariant, CSSProperties> = {
      primary: {
        background: "var(--accent)",
        // --on-accent 随主题翻转：亮色是白字，暗色是深蓝（压在亮蓝底上）
        color: "var(--on-accent)",
        border: "1px solid var(--accent)",
      },
      secondary: {
        background: "var(--bg-surface)",
        color: "var(--text-primary)",
        border: "1px solid var(--border-default)",
      },
      ghost: {
        background: "transparent",
        color: "var(--text-secondary)",
        border: "1px solid transparent",
      },
      danger: {
        background: "var(--danger-solid)",
        // 白字压在深红填充上；--danger（亮）是给文字用的那个
        color: "var(--text-on-accent)",
        border: "1px solid var(--danger-solid)",
      },
    };

    // 按下反馈走 CSS class，不用 JS 改 style。
    // 内联 style 会覆盖样式表里的 :active，导致 transform 永远不生效
    // （实测按下中 transform 一直是 none）。
    //
    // 命中区：sm(28) 和 md(34) 都不够 40px，用伪元素补。
    // lg(42) 已经达标，不用扩。
    const hit = size === "lg" ? "" : " df-hit-v";
    const cls =
      `df-btn df-btn-${variant}${hit}` +
      `${disabled || loading ? " is-disabled" : ""}`;

    return (
      <button
        ref={ref}
        type={type}
        title={title}
        disabled={disabled || loading}
        onClick={onClick}
        className={cls}
        data-variant={variant}
        style={{
          ...palette[variant],
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "var(--space-2)",
          height: BTN_HEIGHT[size],
          minWidth: BTN_HEIGHT[size],
          padding: `0 ${BTN_PX[size]}px`,
          borderRadius: "var(--radius-md)",
          fontSize: BTN_FS[size],
          fontWeight: "var(--weight-normal)",
          lineHeight: 1,
          width: fullWidth ? "100%" : undefined,
          opacity: disabled ? 0.45 : 1,
          /* 伪元素要定位得住 */
          position: "relative",
          /* 触屏上双击缩放会延迟点击响应 */
          touchAction: "manipulation",
        }}
      >
        {loading && <Spinner size={12} />}
        {icon}
        {children}
        {/* 焦点环的淡入层。必须是真的元素 ——
            CSS 压缩器会把 ::focus-visible::after 压成单冒号形式，
            Chrome 碰巧认，别的浏览器不认，实测就静默失效了。 */}
        <span className="df-focus-ring" aria-hidden />
      </button>
    );
  }
);

// ── Spinner ───────────────────────────────────────────────

export function Spinner({ size = 14 }: { size?: number }) {
  return (
    <span
      aria-hidden
      className="df-spin"
      style={{
        width: size,
        height: size,
        border: "2px solid currentColor",
        borderRightColor: "transparent",
        borderRadius: "50%",
        opacity: 0.7,
        // 加载指示器在减少动效下也应该转 —— 规范把它列在
        // 「保留」清单里，因为它承载的是「正在处理」这个信息，
        // 不是装饰。用 0.01ms 保留状态感知又不引发不适。
        animation: `df-spin var(--dur-spin) linear infinite`,
      }}
    />
  );
}

// ── Card ──────────────────────────────────────────────────
// 卡片不加阴影：层级靠表面明度差表达，加阴影在密集列表里会显脏。

export function Card({
  children,
  padded = true,
  style,
  className,
}: {
  children: ReactNode;
  padded?: boolean;
  style?: CSSProperties;
  className?: string;
}) {
  return (
    <div
      className={className}
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-lg)",
        padding: padded ? "var(--space-5)" : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// ── Badge ─────────────────────────────────────────────────

export function Badge({
  children,
  tone = "neutral",
  color,
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "success" | "warning" | "danger";
  color?: string;
}) {
  const tones: Record<string, CSSProperties> = {
    neutral: {
      background: "var(--bg-sunken)",
      color: "var(--text-secondary)",
    },
    // 文字用 accent-text（偏亮）而非 accent（偏暗，是按钮底色用的）
    accent: {
      background: "var(--accent-subtle)",
      color: "var(--accent-text)",
    },
    success: { background: "var(--success-bg)", color: "var(--success)" },
    warning: { background: "var(--warning-bg)", color: "var(--warning)" },
    danger: { background: "var(--danger-bg)", color: "var(--danger)" },
  };
  return (
    <span
      style={{
        ...(color ? { background: "transparent", color } : tones[tone]),
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        height: 20,
        padding: "0 8px",
        borderRadius: "var(--radius-sm)",
        fontSize: "var(--text-2xs)",
        fontWeight: "var(--weight-semibold)",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

// ── Field ─────────────────────────────────────────────────

export const Field = ({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  htmlFor?: string;
}) => {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      <label
        htmlFor={htmlFor}
        style={{
          fontSize: "var(--text-sm)",
          fontWeight: "var(--weight-medium)",
          color: "var(--text-secondary)",
        }}
      >
        {label}
      </label>
      {children}
      {error ? (
        <span
          role="alert"
          style={{ fontSize: "var(--text-xs)", color: "var(--danger)" }}
        >
          {error}
        </span>
      ) : hint ? (
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
          {hint}
        </span>
      ) : null}
    </div>
  );
};

export const Input = forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(function Input({ style, className, ...rest }, ref) {
  return (
    <input
      ref={ref}
      {...rest}
      /* 字号交给 CSS 的 .df-field 管：写成内联就永远赢不了
         窄屏媒体查询，375px 下实测仍是 13px。
         用 !important 压制内联是错的 —— 从源头改。 */
      className={`df-field ${className ?? ""}`.trim()}
      style={{
        /* 高度和字号都走 .df-field：内联 style 会赢过样式表，
           窄屏的 16px 媒体查询就是这么失效的（实测 375px
           下设置页输入框仍是 13px）。 */
        padding: "0 var(--space-3)",
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-md)",
        color: "var(--text-primary)",
        touchAction: "manipulation",
        transition: `border-color var(--dur-base) var(--ease-out),
                    box-shadow var(--dur-base) var(--ease-out)`,
        ...style,
      }}
      onFocus={(e) => {
        e.currentTarget.style.borderColor = "var(--accent)";
        e.currentTarget.style.boxShadow = "0 0 0 3px var(--accent-ring)";
      }}
      onBlur={(e) => {
        e.currentTarget.style.borderColor = "var(--border-default)";
        e.currentTarget.style.boxShadow = "none";
      }}
    />
  );
});

export const Select = forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(function Select({ style, className, children, ...rest }, ref) {
  return (
    <select
      ref={ref}
      {...rest}
      className={`df-field ${className ?? ""}`.trim()}
      style={{
        /* 高度和字号都走 .df-field，理由同 Input。 */
        padding: "0 var(--space-3)",
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-md)",
        color: "var(--text-primary)",
        cursor: "pointer",
        touchAction: "manipulation",
        ...style,
      }}
    >
      {children}
    </select>
  );
});

/** 开关。用 button 而不是 checkbox，才能自己控制外观和焦点环 */
export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      /* 40×24 的开关纵向差 16px，需要 8px 以上的扩展。
         通用 df-hit-v 给 8px，但父级的 overflow 会裁掉一部分，
         实测只到 38px —— 用专用 class 补足。 */
      className="df-hit-toggle"
      style={{
        width: 40,
        height: 24,
        borderRadius: "var(--radius-full)",
        background: checked ? "var(--accent)" : "var(--bg-active)",
        border: "1px solid",
        borderColor: checked ? "var(--accent)" : "var(--border-strong)",
        position: "relative",
        transition: `background var(--dur-base) var(--ease-out),
                    border-color var(--dur-base) var(--ease-out)`,
        opacity: disabled ? 0.5 : 1,
        flexShrink: 0,
        touchAction: "manipulation",
      }}
    >
      {/* 滑块只动 transform。之前动的是 left —— left 是布局属性，
          每一帧都要重排，也违反本项目「只动 transform/opacity」的约定。
          位置固定在 left:2，位移用 translateX 表示。 */}
      <span
        style={{
          position: "absolute",
          top: 2,
          left: 2,
          width: 18,
          height: 18,
          borderRadius: "50%",
          // 滑块跟着反色走：暗色主题开关闭时轨道是亮蓝，滑块要变深
          background: checked ? "var(--on-accent)" : "var(--bg-surface)",
          boxShadow: "var(--shadow-sm)",
          transform: checked ? "translateX(16px)" : "translateX(0)",
          transition: `transform var(--dur-base) var(--ease-out)`,
        }}
      />
      {/* 开关是 40×24 的圆角矩形，outline 会切成直角，
          所以焦点环用它自己的圆角。 */}
      <span
        className="df-focus-ring"
        aria-hidden
        style={{ borderRadius: "var(--radius-full)" }}
      />
    </button>
  );
}

// ── EmptyState ────────────────────────────────────────────

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "var(--space-3)",
        padding: "var(--space-12) var(--space-6)",
        textAlign: "center",
      }}
      className="df-page-in-soft"
    >
      <div style={{ fontSize: 40, opacity: 0.5 }} aria-hidden>
        {icon}
      </div>
      <h3 style={{ fontSize: "var(--text-lg)" }}>{title}</h3>
      <p
        style={{
          fontSize: "var(--text-sm)",
          color: "var(--text-tertiary)",
          maxWidth: "38ch",
          lineHeight: "var(--leading-normal)",
          whiteSpace: "pre-line",
        }}
      >
        {description}
      </p>
      {action && <div style={{ marginTop: "var(--space-2)" }}>{action}</div>}
    </div>
  );
}

// ── SectionTitle ──────────────────────────────────────────

export function SectionTitle({
  children,
  action,
}: {
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: "var(--space-3)",
      }}
    >
      <h3
        style={{
          fontSize: "var(--text-xs)",
          fontWeight: "var(--weight-semibold)",
          color: "var(--text-tertiary)",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
        }}
      >
        {children}
      </h3>
      {action}
    </div>
  );
}
