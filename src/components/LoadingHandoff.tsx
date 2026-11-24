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
import { ReactNode, useEffect, useRef, useState } from "react";
import { useExit } from "@/lib/motion";

const PLACEHOLDER_DELAY = 120;

export function LoadingHandoff({
  loading,
  skeleton,
  children,
}: {
  loading: boolean;
  skeleton: ReactNode;
  children: ReactNode;
}) {
  const [skeletonVisible, setSkeletonVisible] = useState(false);
  const placeholder = useRef<HTMLDivElement>(null);
  useExit(placeholder, !loading && skeletonVisible, () => setSkeletonVisible(false));

  useEffect(() => {
    if (!loading) return;
    const timer = window.setTimeout(() => setSkeletonVisible(true), PLACEHOLDER_DELAY);
    return () => window.clearTimeout(timer);
  }, [loading]);

  return (
    <div className="df-handoff" aria-busy={loading || undefined}>
      {skeletonVisible && (
        <div ref={placeholder} className={loading ? undefined : "df-skeleton-out"}
          aria-hidden="true">
          {skeleton}
        </div>
      )}
      {loading && skeletonVisible && <span className="u-sr-only" role="status">正在加载</span>}
      {!loading && <div className="df-content-in">{children}</div>}
    </div>
  );
}
