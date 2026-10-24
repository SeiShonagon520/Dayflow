/*
 * 视口查询
 *
 * 断点从内容压力来，不从设备名来。这里量过：
 * 侧栏 200px + 内容最小可读宽度 560px = 760px 是导航必须收起的点。
 * 再窄，导航变成底部标签栏 —— 单手够得到，也符合拇指区。
 *
 * 只用 matchMedia，不用 UA 嗅探。窗口尺寸是布局输入，
 * 设备型号不是。
 */
import { useEffect, useState } from "react";

/** 侧栏收成图标栏 */
export const BP_RAIL = 1000;
/** 导航移到屏幕底部，变成标签栏 */
export const BP_BOTTOM = 620;

function useMQ(query: string): boolean {
  const [match, setMatch] = useState(() =>
    typeof window !== "undefined" && window.matchMedia
      ? window.matchMedia(query).matches
      : false);

  useEffect(() => {
    if (!window.matchMedia) return;
    const mq = window.matchMedia(query);
    const on = () => setMatch(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);

  return match;
}

export function useIsNarrow(): boolean {
  return useMQ(`(max-width: ${BP_RAIL - 1}px)`);
}

export function useIsPhone(): boolean {
  return useMQ(`(max-width: ${BP_BOTTOM - 1}px)`);
}

/** 指针是否真的能悬停。触屏设备上 hover 态不能是唯一入口。 */
export function useHasHover(): boolean {
  return useMQ("(hover: hover) and (pointer: fine)");
}
