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

/** 交接时长，和 CSS 里 --dur-handoff 对齐 */
const HANDOFF_MS = 200;

export function LoadingHandoff({
  loading,
  skeleton,
  children,
}: {
  loading: boolean;
  skeleton: ReactNode;
  children: ReactNode;
}) {
  const [skeletonVisible, setSkeletonVisible] = useState(true);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (loading) {
      setSkeletonVisible(true);
    } else if (skeletonVisible) {
      // 内容已经在了，再留骨架 200ms 让它淡出
      timer.current = window.setTimeout(
        () => setSkeletonVisible(false), HANDOFF_MS);
    }
    return () => window.clearTimeout(timer.current);
  }, [loading, skeletonVisible]);

  if (loading) {
    return <>{skeleton}</>;
  }

  return (
    <>
      {/* 骨架还在，但已经透明 —— 它的位置不变，
          内容淡进来盖住它。尺寸对得上所以看不出重叠。 */}
      {skeletonVisible && (
        <div className="df-skeleton-out" aria-hidden="true">
          {skeleton}
        </div>
      )}
      <div className="df-content-in">{children}</div>
    </>
  );
}
