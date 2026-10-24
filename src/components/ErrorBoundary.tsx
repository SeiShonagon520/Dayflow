/*
 * 错误边界
 *
 * 页面组件崩了，不应该连导航和窗口一起消失。实测切到日报页时
 * 一个 undefined.length 就让 .df-shell 从 DOM 消失 —— 整个应用
 * 变成白屏，用户连切回别的页面都做不到。
 *
 * 这里兜住渲染期错误：坏掉的页面替换成一句说明加一个重试，
 * 外壳和导航照常工作。
 */
import { Component, ErrorInfo, ReactNode } from "react";

type Props = {
  children: ReactNode;
  /** 页面名，用于错误文案 */
  label?: string;
  /** 错误后把边界复位，让用户能重试 */
  onReset?: () => void;
};

type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[Dayflow] 渲染出错", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const { label, onReset } = this.props;

    return (
      <div
        role="alert"
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "var(--space-3)",
          padding: "var(--space-8) var(--space-4)",
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: 28, opacity: 0.55 }} aria-hidden>
          ⚠
        </div>
        <div
          style={{
            fontSize: "var(--text-md)",
            fontWeight: "var(--weight-semibold)",
          }}
        >
          {label ? `${label}加载失败` : "这个页面出了点问题"}
        </div>
        {/* 说清是什么坏了、接下来怎么做，不把用户当罪魁 */}
        <div
          style={{
            fontSize: "var(--text-sm)",
            color: "var(--text-tertiary)",
            maxWidth: "38ch",
            lineHeight: 1.6,
          }}
        >
          其它页面不受影响。可以重新载入当前页，或重启 Dayflow。
        </div>
        <code
          style={{
            fontSize: "var(--text-2xs)",
            color: "var(--text-placeholder)",
            maxWidth: "46ch",
            overflowWrap: "anywhere",
            textAlign: "center",
          }}
        >
          {error.message}
        </code>
        <button
          type="button"
          className="df-btn df-btn-primary df-hit-v"
          onClick={() => {
            this.setState({ error: null });
            onReset?.();
          }}
        >
          重新载入
        </button>
      </div>
    );
  }
}
