/*
 * 动效强度控制
 *
 * 三档：跟随系统 / 减少 / 完整。写入 data-motion 到 <html>，
 * 复用统一滑动胶囊 SegmentedControl，支持方向键漫游焦点与零重排滑块平移。
 */
import { useEffect, useState } from "react";

import { MotionLevel, readMotionLevel, saveMotionLevel } from "@/lib/motion";
import { useMQ } from "@/lib/useMediaQuery";
import { SegmentedControl } from "@/components/ui";

const OPTIONS: { value: MotionLevel; label: string; hint: string }[] = [
  { value: "system", label: "跟随系统", hint: "按系统的「减少动态效果」设置" },
  { value: "reduced", label: "减少", hint: "关闭位移、缩放与呼吸效果，保留状态提示" },
  { value: "full", label: "完整", hint: "始终播放全部过渡动画" },
];

/** 设置页里用：三段滑动切换 */
export function MotionControl() {
  const [level, setLevel] = useState(readMotionLevel);
  const systemOn = useMQ("(prefers-reduced-motion: reduce)");

  useEffect(() => saveMotionLevel(level), [level]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)" }}>
            界面动效
          </div>
          <div
            key={`${level}-${systemOn}`}
            className="df-feedback"
            style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", marginTop: 2 }}
          >
            {OPTIONS.find((o) => o.value === level)?.hint}
            {level === "system" && systemOn && "　当前系统：已开启「减少动态效果」"}
          </div>
        </div>
      </div>

      <SegmentedControl
        roleMode="radiogroup"
        label="界面动效强度"
        options={OPTIONS.map(({ value, label }) => ({ value, label }))}
        value={level}
        onChange={setLevel}
      />
    </div>
  );
}
