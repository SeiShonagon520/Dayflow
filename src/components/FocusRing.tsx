/*
 * 焦点环
 *
 * 为什么不是一个 CSS 伪元素：
 *
 * 1. outline 过渡会被组件自己的 transition 简写整体覆盖。
 *    实测 8 处内联 transition 全部让焦点环退回硬切。
 * 2. ::focus-visible::after 会被 Vite 的 CSS 压缩器压成
 *    ::focus-visible:after。Chrome 碰巧认单冒号形式，
 *    CSS 规范里没有 —— 换个浏览器就静默失效（实测 content:none）。
 *
 * 所以焦点环是一个真实的 DOM 节点，在 JSX 里。
 *
 * 注意：不是每个控件都能放子节点 —— <input> 是替换元素，
 * 塞了也不会渲染。Input/Select 那两个改用 CSS 画的
 * .df-field-focus 覆盖层。
 */
export function FocusRing() {
  return <span className="df-focus-ring" aria-hidden="true" />;
}

