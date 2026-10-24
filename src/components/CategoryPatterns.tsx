/*
 * 类别形状（SVG pattern）
 *
 * 为什么需要：8 个类别色在绿色盲/红色盲下会两两靠近 —— 蓝和青在同一条
 * 感知轴上，只换色相区分不了。把颜色重排到可分辨会让配色发灰变脏
 * （实测：娱乐变成粉、会议变成棕），得不偿失。
 *
 * 所以分工是：颜色负责好看，形状负责可辨。每个类别固定一个形状，
 * 图表里色块 + 形状 + 文字三重编码，去掉任意一个都不影响理解。
 */
import { CATEGORY_SHAPE, categoryPatternId } from "@/lib/format";

/** 8 个类别形状的 SVG pattern 定义。挂一次，全站复用。 */
export function CategoryPatterns() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden>
      <defs>
        {Object.entries(CATEGORY_SHAPE).map(([cat, shape]) => (
          <Pattern key={cat} id={categoryPatternId(cat)} shape={shape} />
        ))}
      </defs>
    </svg>
  );
}

function Pattern({ id, shape }: { id: string; shape: string }) {
  // 所有图形都画在 8×8 的方格里，描边用 currentColor 继承类别色
  const s = { stroke: "currentColor", fill: "none" as const };

  switch (shape) {
    case "diagonal":
      return (
        <pattern id={id} width="6" height="6" patternUnits="userSpaceOnUse">
          <path d="M-1,1 l4,-4 M0,6 l6,-6" {...s} strokeWidth="1.6" />
        </pattern>
      );
    case "cross":
      return (
        <pattern id={id} width="6" height="6" patternUnits="userSpaceOnUse">
          <path d="M0,3 h6 M3,0 v6" {...s} strokeWidth="1.4" />
        </pattern>
      );
    case "dots":
      return (
        <pattern id={id} width="5" height="5" patternUnits="userSpaceOnUse">
          <circle cx="1.5" cy="1.5" r="1.2" fill="currentColor" />
          <circle cx="4" cy="4" r="1.2" fill="currentColor" />
        </pattern>
      );
    case "horizontal":
      return (
        <pattern id={id} width="8" height="5" patternUnits="userSpaceOnUse">
          <path d="M0,1.5 h8 M0,4 h8" {...s} strokeWidth="1.5" />
        </pattern>
      );
    case "vertical":
      return (
        <pattern id={id} width="5" height="8" patternUnits="userSpaceOnUse">
          <path d="M1.5,0 v8 M4,0 v8" {...s} strokeWidth="1.5" />
        </pattern>
      );
    case "ring":
      return (
        <pattern id={id} width="6" height="6" patternUnits="userSpaceOnUse">
          <circle cx="3" cy="3" r="1.9" {...s} strokeWidth="1.5" />
        </pattern>
      );
    case "solid-alt":
      // 休息/其他：实心但用极稀疏的网格，和「工作」的纯实心区分开
      return (
        <pattern id={id} width="7" height="7" patternUnits="userSpaceOnUse">
          <path d="M3.5,0 v7 M0,3.5 h7" {...s} strokeWidth="1" />
        </pattern>
      );
    default: // solid
      return <pattern id={id} width="4" height="4" patternUnits="userSpaceOnUse" />;
  }
}
