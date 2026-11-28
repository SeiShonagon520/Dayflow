/*
 * 加载交接
 *
 * 实测（慢网络，30ms 采样）：骨架屏和真实内容**同存 0 帧** ——
 * 骨架一被 React 卸载，内容立刻出现，中间没有任何过渡。
 * 用户看到的是「灰条 → 啪」，加载完成的瞬间像闪了一下。
 *
 * 做法：骨架和内容都留在 DOM 里，交叠一个淡入淡出。
 * 只动 opacity，不动布局。
 */
import { ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useExit } from "@/lib/motion";

const PLACEHOLDER_DELAY = 120;

export function LoadingHandoff({
  loading,
  skeleton,
  children,
  retainOnReload = false,
}: {
  loading: boolean;
  skeleton: ReactNode;
  children: ReactNode;
  retainOnReload?: boolean;
}) {
  const [skeletonVisible, setSkeletonVisible] = useState(false);
  const placeholder = useRef<HTMLDivElement>(null);
  const previous = useRef<ReactNode>(null);
  const content = useRef<HTMLDivElement>(null);
  const retained = retainOnReload && loading && previous.current !== null;
  useExit(placeholder, !loading && skeletonVisible, () => setSkeletonVisible(false));

  useLayoutEffect(() => {
    if (!loading && retainOnReload) previous.current = children;
    content.current?.toggleAttribute("inert", retained);
  }, [children, loading, retained, retainOnReload]);

  useEffect(() => {
    if (!loading || retained) return;
    const timer = window.setTimeout(() => setSkeletonVisible(true), PLACEHOLDER_DELAY);
    return () => window.clearTimeout(timer);
  }, [loading, retained]);

  return (
    <div className="df-handoff">
      <span className="u-sr-only" aria-live="polite">{loading && skeletonVisible ? "正在加载" : ""}</span>
      <span className="df-reload-hint" role="status">
        {retained ? "正在读取…" : ""}
      </span>
      <div aria-busy={loading || undefined}>
        {skeletonVisible && !retained && (
          <div ref={placeholder} className={loading ? undefined : "df-skeleton-out"}
            aria-hidden="true">
            {skeleton}
          </div>
        )}
        {(!loading || retained) && (
          <div ref={content} className={skeletonVisible && !loading ? "df-handoff-content df-content-in" : "df-handoff-content"}
            data-reloading={retained || undefined} aria-hidden={retained || undefined}>
            {retained ? previous.current : children}
          </div>
        )}
      </div>
    </div>
  );
}
