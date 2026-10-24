/*
 * 共享工具
 *
 * 类别色必须全局唯一：时间轴的圆点、统计页的图例、饼图、应用榜单
 * 都要用同一个映射，否则同一个类别在两个页面显示成不同颜色。
 * 这个映射从 CSS token 派生 —— 想改颜色只改 tokens.css。
 */

export const CATEGORIES = [
  "工作",
  "编程",
  "学习",
  "会议",
  "娱乐",
  "社交",
  "休息",
  "其他",
] as const;

export type Category = (typeof CATEGORIES)[number] | string;

/**
 * 每个类别的形状标记。
 *
 * 8 个类别色在绿色盲/红色盲下会两两靠近 —— 蓝和青在同一条感知轴上，
 * 只靠色相区分不了。解决办法不是把颜色调得面目全非（实测会让配色发灰
 * 变脏），而是给每个类别一个固定形状：颜色负责好看，形状负责可辨。
 *
 * 形状在图表里以 SVG pattern 呈现，在纯文字场景（时间轴行）里以
 * 图标呈现 —— 同一套映射，不出现「这里有形状、那里没有」的不一致。
 */
export const CATEGORY_SHAPE: Record<string, string> = {
  工作: "solid",      // 实心
  编程: "diagonal",   // 斜线
  学习: "cross",      // 交叉网格
  会议: "dots",       // 圆点
  娱乐: "horizontal", // 横线
  社交: "vertical",   // 竖线
  休息: "ring",       // 空心圆环
  其他: "solid-alt",  // 反色实心
};

/** 形状对应的 SVG pattern id */
export function categoryPatternId(cat: string): string {
  return `pat-${CATEGORY_SHAPE[cat] ?? "solid-alt"}`;
}

/** 形状对应的图标字符（纯文字场景用） */
export function categoryGlyph(cat: string): string {
  const map: Record<string, string> = {
    solid: "■",
    diagonal: "◩",
    cross: "◫",
    dots: "⁘",
    horizontal: "≡",
    vertical: "▤",
    ring: "○",
    "solid-alt": "□",
  };
  return map[CATEGORY_SHAPE[cat] ?? "solid-alt"] ?? "□";
}

/** 类别 → CSS 变量名。取不到就落到「其他」的灰。 */
export function categoryVar(cat: string): string {
  const map: Record<string, string> = {
    工作: "--cat-work",
    编程: "--cat-code",
    学习: "--cat-study",
    会议: "--cat-meeting",
    娱乐: "--cat-media",
    社交: "--cat-social",
    休息: "--cat-rest",
    其他: "--cat-other",
    Work: "--cat-work",
    Coding: "--cat-code",
    Study: "--cat-study",
    Meeting: "--cat-meeting",
    Entertainment: "--cat-media",
    Social: "--cat-social",
    Break: "--cat-rest",
    Other: "--cat-other",
  };
  return map[cat] ?? "--cat-other";
}

/** 类别 → 实际色值（图表 canvas 用，需要具体字符串） */
export function categoryColor(cat: string): string {
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(categoryVar(cat))
    .trim();
  return v || "#6e6e73";
}

// ── 日期 ──────────────────────────────────────────────────

export function todayStr(): string {
  return toDateStr(new Date());
}

export function toDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function shiftDate(dateStr: string, days: number): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, m - 1, d + days);
  return toDateStr(dt);
}

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

export function weekdayOf(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  return WEEKDAYS[new Date(y, m - 1, d).getDay()];
}

export function prettyDate(dateStr: string): string {
  const [, m, d] = dateStr.split("-").map(Number);
  return `${m} 月 ${d} 日`;
}

export function fullDate(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  return `${y} 年 ${m} 月 ${d} 日 ${weekdayOf(dateStr)}`;
}

export function isToday(dateStr: string): boolean {
  return dateStr === todayStr();
}

// ── 时长 ──────────────────────────────────────────────────

export function formatMinutes(mins: number): string {
  if (mins <= 0) return "0m";
  const h = Math.floor(mins / 60);
  const m = Math.round(mins % 60);
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

export function formatClock(iso: string | null): string {
  if (!iso) return "--:--";
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes()
  ).padStart(2, "0")}`;
}

// ── 生产力分档 ──────────────────────────────────────────────
// 界面上必须同时用「颜色 + 文字」表示档位，不能只靠色相。

export type ScoreBand = "high" | "mid" | "low";

export function scoreBand(score: number): ScoreBand {
  if (score >= 70) return "high";
  if (score >= 40) return "mid";
  return "low";
}

export function scoreLabel(score: number): string {
  if (score >= 70) return "高效";
  if (score >= 40) return "一般";
  return "低效";
}

export function scoreVar(score: number): string {
  const b = scoreBand(score);
  return b === "high"
    ? "--success"
    : b === "mid"
    ? "--warning"
    : "--text-tertiary";
}
