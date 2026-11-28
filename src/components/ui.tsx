/*
 * 基础 UI 组件
 *
 * 全部只用 token，不写死任何色值/像素值；
 * 所有交互态和过渡统一收口到 CSS class，确保跟手、可打断且尊重 reduced-motion。
 */

import {
  CSSProperties,
  ReactNode,
  forwardRef,
  useCallback,
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { LineIcon } from "@/components/LineIcon";
import { useSurfaceEnter } from "@/lib/motion";

// ── Button ────────────────────────────────────────────────

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  disabled?: boolean;
  loading?: boolean;
  children?: ReactNode;
  onClick?: () => void;
  title?: string;
  fullWidth?: boolean;
  "aria-label"?: string;
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
      children,
      onClick,
      title,
      fullWidth,
      "aria-label": ariaLabel,
    },
    ref
  ) {
    const palette: Record<ButtonVariant, CSSProperties & { "--df-button-bg": string }> = {
      primary: {
        "--df-button-bg": "var(--accent)",
        color: "var(--text-on-accent)",
        border: "1px solid var(--accent)",
      },
      secondary: {
        "--df-button-bg": "var(--bg-surface)",
        color: "var(--text-primary)",
        border: "1px solid var(--border-default)",
      },
      ghost: {
        "--df-button-bg": "transparent",
        color: "var(--text-secondary)",
        border: "1px solid transparent",
      },
      danger: {
        "--df-button-bg": "var(--danger-solid)",
        color: "#fff",
        border: "1px solid var(--danger-solid)",
      },
    };

    const hit = size === "lg" ? "" : " df-hit-v";
    const cls =
      `df-btn${hit}` +
      `${disabled || loading ? " is-disabled" : ""}`;

    return (
      <button
        ref={ref}
        type="button"
        title={title}
        aria-label={ariaLabel}
        aria-busy={loading || undefined}
        aria-disabled={loading || undefined}
        disabled={disabled}
        onClick={loading ? (event) => event.preventDefault() : onClick}
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
          position: "relative",
          touchAction: "manipulation",
        }}
      >
        <span className="df-busy-content">
          <span className="df-button-label" data-hidden={loading || undefined}>
            {children}
          </span>
          <span className="df-busy-spinner" data-visible={loading || undefined} aria-hidden="true">
            {loading && <Spinner size={12} />}
          </span>
        </span>
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
        opacity: 0.72,
      }}
    />
  );
}

// ── IconSwap ──────────────────────────────────────────────
// 同位双态图标交叉淡化（纯 opacity + scale，零重排）

export function IconSwap({
  active,
  first,
  second,
  size = 16,
}: {
  active: boolean;
  first: ReactNode;
  second: ReactNode;
  size?: number;
}) {
  return (
    <span
      className="df-icon-swap"
      data-swapped={active ? "true" : "false"}
      aria-hidden="true"
      style={{ width: size, height: size }}
    >
      <span className="df-icon-swap-a">{first}</span>
      <span className="df-icon-swap-b">{second}</span>
    </span>
  );
}

// ── SegmentedControl ──────────────────────────────────────
// Apple 风格滑动胶囊分段控件：等宽网格 + 纯 GPU transform 平移滑块，
// 零布局重排、随时可打断、完整方向键漫游焦点支持。

export function SegmentedControl<T extends string | number>({
  options,
  value,
  onChange,
  label,
  roleMode = "tablist",
  compact = false,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  roleMode?: "tablist" | "radiogroup";
  compact?: boolean;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const activeIndex = Math.max(0, options.findIndex((o) => o.value === value));
  const itemRole = roleMode === "tablist" ? "tab" : "radio";

  const onKeyDown = (e: React.KeyboardEvent) => {
    const dir =
      e.key === "ArrowRight" || (roleMode === "radiogroup" && e.key === "ArrowDown") ? 1
      : e.key === "ArrowLeft" || (roleMode === "radiogroup" && e.key === "ArrowUp") ? -1
      : 0;
    if (dir === 0) return;
    e.preventDefault();
    const next = (activeIndex + dir + options.length) % options.length;
    onChange(options[next].value);
    requestAnimationFrame(() => refs.current[next]?.focus());
  };

  return (
    <div
      role={roleMode}
      aria-label={label}
      onKeyDown={onKeyDown}
      className={`df-segmented${compact ? " is-compact" : ""}`}
      style={
        {
          "--seg-count": options.length,
          "--seg-index": activeIndex,
        } as CSSProperties
      }
    >
      <span aria-hidden className="df-segmented-thumb" />
      {options.map((o, i) => {
        const active = o.value === value;
        return (
          <button
            key={String(o.value)}
            ref={(el) => { refs.current[i] = el; }}
            type="button"
            role={itemRole}
            aria-selected={itemRole === "tab" ? active : undefined}
            aria-checked={itemRole === "radio" ? active : undefined}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(o.value)}
            className="df-hit-v df-segmented-item"
            data-active={active ? "true" : "false"}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Card ──────────────────────────────────────────────────

export function Card({
  children,
  variant = "surface",
  className,
  style,
}: {
  children: ReactNode;
  variant?: "surface" | "inset" | "flush";
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      className={`df-card ${className ?? ""}`.trim()}
      data-variant={variant}
      style={style}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
  icon,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="df-card-head">
      <div className="df-card-head-main">
        <div className="df-card-title-row">
          {icon}
          <h3 className="df-card-title">{title}</h3>
        </div>
        {description && <p className="df-card-desc">{description}</p>}
      </div>
      {action && <div className="df-card-head-action">{action}</div>}
    </div>
  );
}

export function CardBody({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`df-card-body ${className ?? ""}`.trim()}>{children}</div>;
}

export function CardFooter({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`df-card-foot ${className ?? ""}`.trim()}>{children}</div>;
}

// ── Badge & MetaChip & Kbd ────────────────────────────────

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "success" | "warning" | "danger";
  className?: string;
}) {
  return (
    <span className={`df-badge ${className ?? ""}`.trim()} data-tone={tone}>
      {children}
    </span>
  );
}

export function MetaChip({
  children,
  className,
  title,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span className={`df-chip ${className ?? ""}`.trim()} title={title}>
      {children}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="df-kbd">{children}</kbd>;
}

// ── Tooltip ───────────────────────────────────────────────
// 替代原生 title：Portal 挂载避免被 overflow:hidden 裁切，
// 支持悬停与键盘聚焦双触发，纯 opacity + transform 过渡。

export function Tooltip({
  content,
  placement = "top",
  disabled = false,
  children,
}: {
  content: ReactNode;
  placement?: "top" | "bottom" | "right";
  disabled?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<{ x: number; y: number } | null>(null);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const timerRef = useRef<number | null>(null);
  const tooltipId = useId();

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const updatePosition = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const gap = 8;
    let x = rect.left + rect.width / 2;
    let y = rect.top - gap;
    if (placement === "bottom") {
      y = rect.bottom + gap;
    } else if (placement === "right") {
      x = rect.right + gap;
      y = rect.top + rect.height / 2;
    }
    x = Math.max(12, Math.min(window.innerWidth - 12, x));
    y = Math.max(12, Math.min(window.innerHeight - 12, y));
    setCoords({ x, y });
  }, [placement]);

  const show = (immediate: boolean) => {
    if (disabled || !content) return;
    clearTimer();
    const run = () => {
      updatePosition();
      setOpen(true);
    };
    if (immediate) run();
    else timerRef.current = window.setTimeout(run, 140);
  };

  const hide = useCallback(() => {
    clearTimer();
    setOpen(false);
  }, [clearTimer]);

  useEffect(() => () => clearTimer(), [clearTimer]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") hide();
    };
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [open, hide]);

  useEffect(() => {
    if (disabled && open) hide();
  }, [disabled, open, hide]);

  return (
    <span
      ref={triggerRef}
      className="df-tooltip-trigger"
      aria-describedby={open ? tooltipId : undefined}
      onMouseEnter={() => show(false)}
      onMouseLeave={hide}
      onFocus={(event) => {
        if (event.target.matches(":focus-visible")) show(true);
      }}
      onBlur={hide}
      onPointerDown={hide}
    >
      {children}
      {open && coords && createPortal(
        <span
          id={tooltipId}
          role="tooltip"
          className="df-tooltip"
          data-placement={placement}
          style={{ left: coords.x, top: coords.y }}
        >
          {content}
        </span>,
        document.body,
      )}
    </span>
  );
}

// ── NumberStepper ─────────────────────────────────────────
// 借鉴 Rare UI Duration Picker 的步进结构，剥离弹跳物理，
// 收口为 1px 发丝精密桌面步进器 + 可选快捷预设胶囊。

export function NumberStepper({
  id,
  value,
  onChange,
  min,
  max,
  step = 1,
  unit,
  presets,
  disabled,
  ariaLabel,
}: {
  id?: string;
  value: string | number;
  onChange: (value: string) => void;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  presets?: number[];
  disabled?: boolean;
  ariaLabel?: string;
}) {
  const numeric = Number(value);
  const valid = Number.isFinite(numeric);
  const canDec = !disabled && (!valid || numeric > min);
  const canInc = !disabled && (!valid || numeric < max);

  const nudge = (delta: number) => {
    const base = valid ? numeric : min;
    const next = Math.max(min, Math.min(max, base + delta));
    onChange(String(next));
  };

  return (
    <div className="df-stepper-wrap">
      <div className="df-stepper" data-disabled={disabled ? "true" : undefined}>
        <button
          type="button"
          className="df-stepper-btn"
          aria-label="减少"
          disabled={!canDec}
          onClick={() => nudge(-step)}
        >
          <LineIcon name="minus" size={14} />
        </button>
        <input
          id={id}
          type="number"
          inputMode="numeric"
          aria-label={ariaLabel}
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="df-stepper-input u-tabular"
        />
        {unit && <span className="df-stepper-unit" aria-hidden="true">{unit}</span>}
        <button
          type="button"
          className="df-stepper-btn"
          aria-label="增加"
          disabled={!canInc}
          onClick={() => nudge(step)}
        >
          <LineIcon name="plus" size={14} />
        </button>
      </div>
      {presets && presets.length > 0 && (
        <div className="df-stepper-presets">
          {presets.map((preset) => {
            const active = valid && numeric === preset;
            return (
              <button
                key={preset}
                type="button"
                disabled={disabled}
                aria-pressed={active}
                className="df-stepper-preset u-tabular"
                onClick={() => onChange(String(preset))}
              >
                {preset}{unit ?? ""}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Toast ─────────────────────────────────────────────────
// 统一全局报错（顶部通道）与限时撤销（底部通道）原语，
// 零内联定位散落，共享 useExit 退场与悬停暂停倒计时语义。

export const Toast = forwardRef<
  HTMLDivElement,
  {
    variant?: "default" | "danger";
    position?: "top" | "bottom";
    closing?: boolean;
    paused?: boolean;
    countdownKey?: string | number;
    reducedHint?: string;
    icon?: ReactNode;
    action?: ReactNode;
    role?: "status" | "alert";
    ariaLive?: "polite" | "assertive";
    onMouseEnter?: React.MouseEventHandler<HTMLDivElement>;
    onMouseLeave?: React.MouseEventHandler<HTMLDivElement>;
    onFocus?: React.FocusEventHandler<HTMLDivElement>;
    onBlur?: React.FocusEventHandler<HTMLDivElement>;
    children: ReactNode;
  }
>(function Toast(
  {
    variant = "default",
    position = "bottom",
    closing,
    paused,
    countdownKey,
    reducedHint,
    icon,
    action,
    role = variant === "danger" ? "alert" : "status",
    ariaLive = variant === "danger" ? "assertive" : "polite",
    onMouseEnter,
    onMouseLeave,
    onFocus,
    onBlur,
    children,
  },
  ref,
) {
  const posClass = position === "top" ? "df-error-toast" : "df-undo-toast";
  const root = useRef<HTMLDivElement>(null);
  useImperativeHandle(ref, () => root.current!, []);
  useSurfaceEnter(root);
  return createPortal(
    <div
      ref={root}
      role={role}
      aria-live={ariaLive}
      data-closing={closing || undefined}
      data-paused={paused || undefined}
      data-variant={variant}
      data-countdown={countdownKey !== undefined ? "true" : undefined}
      className={`df-toast df-toast-shell ${posClass}`}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onFocus={onFocus}
      onBlur={onBlur}
    >
      {icon && <span className="df-toast-icon" aria-hidden="true">{icon}</span>}
      <span className="df-toast-text">
        {children}
        {reducedHint && <span className="df-undo-reduced-hint">{reducedHint}</span>}
      </span>
      {action}
      {countdownKey !== undefined && (
        <span key={countdownKey} aria-hidden="true" className="df-undo-timer" />
      )}
    </div>,
    document.body,
  );
});

// ── ChartPopover ──────────────────────────────────────────
// 统计图表统一悬浮读数卡（纯 CSS 定位与 GPU 过渡，自动贴边防溢出）

export function ChartPopover({
  xPct,
  yPx,
  title,
  value,
  meta,
  color,
  glyph,
}: {
  xPct: number;
  yPx: number;
  title: string;
  value: string;
  meta?: string;
  color?: string;
  glyph?: string;
}) {
  const align = xPct < 22 ? "left" : xPct > 78 ? "right" : "center";
  return (
    <div
      className="df-chart-popover"
      data-align={align}
      style={{
        left: `${Math.max(4, Math.min(96, xPct))}%`,
        top: `${Math.max(0, yPx)}px`,
      }}
      role="status"
      aria-live="polite"
    >
      <div className="df-chart-popover-head">
        {color && (
          <span className="df-chart-popover-swatch" style={{ color }} aria-hidden="true">
            {glyph ?? "●"}
          </span>
        )}
        <span className="df-chart-popover-title">{title}</span>
      </div>
      <div className="df-chart-popover-value u-tabular">{value}</div>
      {meta && <div className="df-chart-popover-meta u-tabular">{meta}</div>}
    </div>
  );
}

// ── Field ─────────────────────────────────────────────────

export const Field = ({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
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
      {hint ? (
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
      className={`df-field ${className ?? ""}`.trim()}
      style={{
        padding: "0 var(--space-3)",
        background: "var(--bg-surface)",
        borderRadius: "var(--radius-md)",
        color: "var(--text-primary)",
        touchAction: "manipulation",
        ...style,
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
        padding: "0 var(--space-3)",
        background: "var(--bg-surface)",
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

/** 开关：按住时向轨道内侧拉伸（左关向右伸、右开向左伸），不越出边界 */
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
      className="df-hit-toggle df-toggle"
      data-checked={checked ? "true" : "false"}
      style={{
        width: 40,
        height: 24,
        borderRadius: "var(--radius-full)",
        background: checked ? "var(--accent)" : "var(--bg-active)",
        border: "1px solid",
        borderColor: checked ? "var(--accent)" : "var(--border-strong)",
        position: "relative",
        transition: `background var(--dur-fast) var(--ease-out),
                    border-color var(--dur-fast) var(--ease-out)`,
        opacity: disabled ? 0.5 : 1,
        flexShrink: 0,
        touchAction: "manipulation",
      }}
    >
      <span
        className="df-toggle-knob"
        style={{
          position: "absolute",
          top: 2,
          left: 2,
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: checked ? "var(--text-on-accent)" : "var(--bg-surface)",
          boxShadow: "var(--shadow-sm)",
          transformOrigin: checked ? "right center" : "left center",
          transform: `translateX(${checked ? 16 : 0}px) scaleX(var(--knob-press, 1))`,
          transition: `transform var(--dur-fast) var(--ease-out),
                      background var(--dur-fast) var(--ease-out)`,
        }}
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
      <div
        style={{
          color: "var(--text-tertiary)",
          opacity: 0.7,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
        aria-hidden
      >
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
