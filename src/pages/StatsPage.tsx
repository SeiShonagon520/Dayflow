/*
 * 统计页
 *
 * 布局遵循「先结论后细节」：顶部四个指标给出全局判断，
 * 下面才是分布、趋势、明细。没有把所有图表平铺成等权重的大格子 ——
 * 那样扫一眼不知道该看哪个。
 *
 * 图表用内联 SVG 而不是图表库：没有依赖，token 直接生效，
 * 而且颜色/圆角/间距都受设计系统管，不会出现「库里的默认蓝」。
 */

import { useEffect, useRef, useState } from "react";
import { ApiError, Stats, api } from "@/lib/api";
import {
  categoryPatternId,
  categoryVar,
  formatMinutes,
  fullDate,
  scoreVar,
} from "@/lib/format";
import { Card, EmptyState, SectionTitle, Spinner } from "@/components/ui";
import { CategoryPatterns } from "@/components/CategoryPatterns";
import { useIsPhone } from "@/lib/useMediaQuery";
import { FocusRing } from "@/components/FocusRing";

export function StatsPage() {
  // 类别形状的 pattern 定义挂在页面根部，全页图表共用
  const patterns = <CategoryPatterns />;
  const [days, setDays] = useState<7 | 30>(7);
  const [data, setData] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  /* 重新取数（切周期）与首次加载是两种状态：
     前者保留旧内容压暗，后者才显示骨架。 */
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (d: 7 | 30) => {
    /* 只在第一次加载时卸载整页。
       之后切换周期时保留旧数据、压暗显示 ——
       否则整页会被卸载重建，工具栏连同方向键焦点一起消失，
       键盘用户按一次右箭头就被丢回 body。 */
    if (data === null) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      setData(await api.getStats(d));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "加载失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    load(days);
  }, [days]);

  // Hook 必须在所有 early return 之前调用。
  // 放在后面时，加载中的那一帧会少一个 hook，React 抛
  // "Rendered more hooks than during the previous render"，整页白掉。
  const phone = useIsPhone();

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 80 }}>
        {patterns}
        <Spinner size={20} />
      </div>
    );
  }

  if (error) {
    return (
      <EmptyState
        icon="⚠️"
        title="统计数据加载失败"
        description={error}
        action={<button onClick={() => load(days)}>重试</button>}
      />
    );
  }

  if (!data || data.metrics?.activityCount === 0) {
    return (
      <EmptyState
        icon="◔"
        title={`最近 ${days} 天没有活动记录`}
        description="开始录制后，这里会显示时间分布、专注趋势和应用使用排行。"
      />
    );
  }

  const m = data.metrics;

  return (
    <div style={{ overflowY: "auto", height: "100%" }}>
      {patterns}
      {/* ── 工具栏 ───────────────────────────────────
          窄屏换行：标题、日期范围、周期切换三件事挤一行时，
          320px 下标题被压成「统」「计」竖排两行。 */}
      <div
        className="df-toolbar"
        data-stacked={phone ? "true" : "false"}
      >
        <div className="df-toolbar-row">
          <h2 className="df-page-title">统计</h2>
          <span
            className="df-page-subtitle"
            style={{ fontSize: "var(--text-sm)", color: "var(--text-tertiary)" }}
          >
            {data.rangeStart} → {data.rangeEnd}
          </span>
          <div className="df-toolbar-spacer" />
          <Segmented
            options={[
              { value: 7, label: "近 7 天" },
              { value: 30, label: "近 30 天" },
            ]}
            value={days}
            onChange={(v) => setDays(v as 7 | 30)}
            label="统计区间"
          />
        </div>
      </div>

      <div
        className="df-content-pad"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-6)",
          /* 重新取数时压暗旧内容，而不是卸载它。
             卸载会让整页高度塌陷再撑开，滚动位置也跟着跳。 */
          opacity: refreshing ? 0.55 : 1,
          transition: "opacity var(--dur-base) var(--ease-out)",
          pointerEvents: refreshing ? "none" : undefined,
        }}
        aria-busy={refreshing || undefined}
      >
        {/* ── 指标卡 ─────────────────────────────── */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
            gap: "var(--space-4)",
          }}
        >
          <Metric
            label="总时长"
            value={`${m.totalHours}`}
            unit="小时"
            change={data.changes.totalHours}
            color="var(--cat-work)"
          />
          <Metric
            label="平均生产力"
            value={`${m.avgScore}`}
            unit="分"
            change={data.changes.avgScore}
            color={`var(${scoreVar(m.avgScore)})`}
          />
          <Metric
            label="深度工作"
            value={`${m.deepWork}`}
            unit="段"
            hint="单段 ≥ 60 分钟"
            change={data.changes.deepWork}
            color="var(--cat-study)"
          />
          <Metric
            label="活动条数"
            value={`${m.activityCount}`}
            unit="条"
            change={data.changes.activityCount}
            color="var(--cat-meeting)"
          />
        </div>

        {/* ── 分布 + 趋势 ────────────────────────── */}
        <div
          className="df-chart-grid df-chart-grid-a"
          style={{
            display: "grid",
            gap: "var(--space-4)",
            alignItems: "start",
          }}
        >
          <Card>
            <SectionTitle>类别分布</SectionTitle>
            <Donut data={data.categories} total={m.totalHours * 60} />
          </Card>

          <Card>
            <SectionTitle>生产力趋势</SectionTitle>
            <Trend data={data.trend} />
          </Card>
        </div>

        {/* ── 贡献日历 + 热力 ─────────────────────── */}
        <div
          className="df-chart-grid df-chart-grid-b"
          style={{
            display: "grid",
            gap: "var(--space-4)",
            alignItems: "start",
          }}
        >
          <Card>
            <SectionTitle>每日投入</SectionTitle>
            <Calendar data={data.calendar} />
          </Card>

          <Card>
            <SectionTitle>时段分布</SectionTitle>
            <Hourly data={data.hourly} />
          </Card>
        </div>

        {/* ── 应用排行 ────────────────────────────── */}
        <Card>
          <SectionTitle>应用使用排行</SectionTitle>
          <AppRanking data={data.appRanking} />
        </Card>
      </div>
    </div>
  );
}

// ── 指标卡 ────────────────────────────────────────────────────

function Metric({
  label,
  value,
  unit,
  change,
  hint,
  color,
}: {
  label: string;
  value: string;
  unit: string;
  change?: number;
  hint?: string;
  color: string;
}) {
  const up = (change ?? 0) >= 0;
  return (
    <Card>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginBottom: "var(--space-2)",
        }}
      >
        <span
          aria-hidden
          style={{ width: 8, height: 8, borderRadius: "50%", background: color }}
        />
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
          {label}
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
        <span
          className="u-tabular"
          style={{ fontSize: "var(--text-2xl)", fontWeight: "var(--weight-semibold)" }}
        >
          {value}
        </span>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--text-tertiary)" }}>
          {unit}
        </span>
      </div>

      {change !== undefined && Math.abs(change) > 0.1 && (
        <div
          style={{
            marginTop: 6,
            fontSize: "var(--text-xs)",
            // 涨跌用「箭头 + 文字」而不是只靠颜色
            color: up ? "var(--success)" : "var(--danger)",
          }}
        >
          {up ? "↑" : "↓"} {Math.abs(change).toFixed(0)}% 较上一周期
        </div>
      )}
      {hint && (
        <div style={{ marginTop: 6, fontSize: "var(--text-2xs)", color: "var(--text-placeholder)" }}>
          {hint}
        </div>
      )}
    </Card>
  );
}

// ── 环形图 ────────────────────────────────────────────────────

function Donut({
  data,
  total,
}: {
  data: { name: string; minutes: number }[];
  total: number;
}) {
  const size = 168;
  const stroke = 22;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;

  let offset = 0;
  const arcs = data.map((d) => {
    const frac = total > 0 ? d.minutes / total : 0;
    const arc = { ...d, dash: frac * c, offset };
    offset += frac * c;
    return arc;
  });

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-5)",
        flexWrap: "wrap",
      }}
    >
      <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
        <svg width={size} height={size} role="img" aria-label="类别分布环形图">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--bg-sunken)"
            strokeWidth={stroke}
          />
          {arcs.map((a) => (
            <circle
              key={a.name}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={`var(${categoryVar(a.name)})`}
              strokeWidth={stroke}
              strokeDasharray={`${a.dash} ${c - a.dash}`}
              strokeDashoffset={-a.offset}
              // 起点在 12 点方向，顺时针
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
            >
              <title>
                {a.name}：{formatMinutes(a.minutes)}
              </title>
            </circle>
          ))}
        </svg>
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <span
            className="u-tabular"
            style={{ fontSize: "var(--text-xl)", fontWeight: "var(--weight-semibold)" }}
          >
            {data.length}
          </span>
          <span style={{ fontSize: "var(--text-2xs)", color: "var(--text-tertiary)" }}>
            个类别
          </span>
        </div>
      </div>

      <Legend items={data.map((d) => ({
        label: d.name,
        value: formatMinutes(d.minutes),
        color: `var(${categoryVar(d.name)})`,
      }))} />
    </div>
  );
}

// ── 趋势折线 ──────────────────────────────────────────────────

function Trend({ data }: { data: { date: string; score: number; hours: number }[] }) {
  const w = 460;
  const h = 150;
  const pad = { t: 12, r: 12, b: 24, l: 30 };

  if (data.length === 0) return null;

  const maxScore = Math.max(100, ...data.map((d) => d.score));
  const stepX =
    data.length > 1 ? (w - pad.l - pad.r) / (data.length - 1) : 0;
  const hasMissing = data.some((d) => d.hours <= 0);
  const segments: number[][] = [];
  let segment: number[] = [];
  data.forEach((d, i) => {
    if (d.hours > 0) {
      segment.push(i);
    } else if (segment.length > 0) {
      segments.push(segment);
      segment = [];
    }
  });
  if (segment.length > 0) segments.push(segment);
  const labelIndices = [...new Set([0, Math.floor((data.length - 1) / 2), data.length - 1])];

  const pt = (i: number, v: number) => [
    pad.l + i * stepX,
    pad.t + (1 - v / maxScore) * (h - pad.t - pad.b),
  ];

  return (
    <div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        width="100%"
        height={h}
        role="img"
        aria-label={
          hasMissing
            ? "生产力趋势折线图，断点表示未记录"
            : "生产力趋势折线图"
        }
      >
        {[0, 0.5, 1].map((f) => {
          const y = pad.t + f * (h - pad.t - pad.b);
          return (
            <g key={f}>
              <line
                x1={pad.l}
                x2={w - pad.r}
                y1={y}
                y2={y}
                stroke="var(--border-subtle)"
                strokeWidth={1}
              />
              <text
                x={pad.l - 6}
                y={y + 3}
                textAnchor="end"
                fontSize={9}
                fill="var(--text-placeholder)"
              >
                {Math.round(maxScore * (1 - f))}
              </text>
            </g>
          );
        })}

        {segments.map((indices, segmentIndex) => {
          const points = indices.map((i) => pt(i, data[i].score).join(",")).join(" ");
          const first = pt(indices[0], data[indices[0]].score);
          const last = pt(indices[indices.length - 1], data[indices[indices.length - 1]].score);
          const area = `${first[0]},${h - pad.b} ${points} ${last[0]},${h - pad.b}`;

          return (
            <g key={segmentIndex}>
              {indices.length > 1 && (
                <>
                  <polygon points={area} fill="var(--accent-subtle)" />
                  <polyline
                    points={points}
                    fill="none"
                    stroke="var(--accent)"
                    strokeWidth={2}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                </>
              )}
              {indices.map((i) => {
                const [x, y] = pt(i, data[i].score);
                return (
                  <circle key={data[i].date} cx={x} cy={y} r={3} fill="var(--accent)" stroke="var(--bg-surface)" strokeWidth={1.2}>
                    <title>
                      {data[i].date}：{data[i].score} 分 / {data[i].hours} 小时
                    </title>
                  </circle>
                );
              })}
            </g>
          );
        })}

        {labelIndices.map((i) => (
          <text
            key={`${data[i].date}-label`}
            x={pad.l + i * stepX}
            y={h - 8}
            textAnchor="middle"
            fontSize={9}
            fill="var(--text-placeholder)"
          >
            {data[i].date.slice(5)}
          </text>
        ))}
      </svg>
      {hasMissing && (
        <div
          style={{
            textAlign: "right",
            fontSize: "var(--text-2xs)",
            color: "var(--text-tertiary)",
          }}
        >
          断点表示未记录
        </div>
      )}
    </div>
  );
}

// ── 贡献日历 ──────────────────────────────────────────────────

function Calendar({
  data,
}: {
  data: { date: string; hours: number; score: number; count: number }[];
}) {
  const cell = 13;
  const gap = 3;
  const weeks = Math.ceil(data.length / 7);
  const maxH = Math.max(1, ...data.map((d) => d.hours));

  const level = (hours: number) => {
    if (hours <= 0) return "var(--bg-sunken)";
    const f = hours / maxH;
    // 用 4 档透明度而不是连续色阶 —— 色阶在小方块上分辨不出
    return `color-mix(in srgb, var(--success) ${Math.round(25 + f * 75)}%, var(--bg-sunken))`;
  };

  return (
    <div>
      <div
        style={{
          display: "grid",
          gridTemplateRows: `repeat(7, ${cell}px)`,
          gridAutoFlow: "column",
          gap,
          overflowX: "auto",
        }}
      >
        {data.map((d) => (
          <div
            key={d.date}
            title={`${fullDate(d.date)}\n${d.hours} 小时 · ${d.score} 分 · ${d.count} 条`}
            style={{
              width: cell,
              height: cell,
              borderRadius: 3,
              background: level(d.hours),
            }}
          />
        ))}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 4,
          marginTop: "var(--space-3)",
          fontSize: "var(--text-2xs)",
          color: "var(--text-tertiary)",
        }}
      >
        少
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <div
            key={f}
            style={{
              width: 10,
              height: 10,
              borderRadius: 2,
              background:
                f === 0
                  ? "var(--bg-sunken)"
                  : `color-mix(in srgb, var(--success) ${Math.round(25 + f * 75)}%, var(--bg-sunken))`,
            }}
          />
        ))}
        多
        <span style={{ marginLeft: "auto" }}>
          近 {weeks} 周
        </span>
      </div>
    </div>
  );
}

// ── 时段热力 ──────────────────────────────────────────────────

function Hourly({ data }: { data: { score: number; minutes: number }[][] }) {
  const maxMin = Math.max(1, ...data.map((h) =>
    h.reduce((s, x) => s + x.minutes, 0)
  ));

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(24, minmax(0, 1fr))",
        gap: 2,
        alignItems: "end",
        height: 108,
      }}
      role="img"
      aria-label="24 小时时段分布"
    >
      {data.map((hour, hi) => {
        const mins = hour.reduce((s, x) => s + x.minutes, 0);
        const h = Math.max(3, (mins / maxMin) * 76);
        return (
          <div key={hi} style={{ display: "flex", flexDirection: "column", justifyContent: "flex-end", height: "100%" }}>
            <div
              title={`${hi}:00 · ${formatMinutes(mins)}`}
              style={{
                height: h,
                borderRadius: 3,
                background:
                  mins > 0 ? "var(--accent)" : "var(--bg-sunken)",
                opacity: mins > 0 ? 0.4 + (mins / maxMin) * 0.6 : 1,
              }}
            />
          </div>
        );
      })}
    </div>
  );
}

// ── 应用排行 ──────────────────────────────────────────────────

function AppRanking({
  data,
}: {
  data: { name: string; minutes: number }[];
}) {
  const top = data.slice(0, 10);
  const max = Math.max(1, ...top.map((d) => d.minutes));

  if (top.length === 0) {
    return <p style={{ fontSize: "var(--text-sm)", color: "var(--text-tertiary)" }}>暂无数据</p>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
      {top.map((d, i) => (
        <div key={d.name} style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <span
            className="u-tabular"
            style={{
              width: 20,
              fontSize: "var(--text-xs)",
              color: "var(--text-tertiary)",
              textAlign: "right",
            }}
          >
            {i + 1}
          </span>
          <span
            className="df-rank-name"
            style={{
              fontSize: "var(--text-sm)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
            title={d.name}
          >
            {d.name}
          </span>
          <div
            style={{ flex: 1, height: 8, background: "var(--bg-sunken)", borderRadius: "var(--radius-full)" }}
          >
            <div
              style={{
                width: `${(d.minutes / max) * 100}%`,
                height: "100%",
                background: "var(--accent)",
                borderRadius: "var(--radius-full)",
                transition: "width var(--dur-space) var(--ease-out)",
              }}
            />
          </div>
          <span
            className="u-tabular"
            style={{ width: 56, fontSize: "var(--text-xs)", color: "var(--text-secondary)", textAlign: "right" }}
          >
            {formatMinutes(d.minutes)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── 通用小部件 ────────────────────────────────────────────────

function Legend({
  items,
}: {
  items: { label: string; value: string; color: string }[];
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1, minWidth: 140 }}>
      {items.map((it) => (
        <div key={it.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {/* 色块 + 形状：色盲下靠形状区分，不靠色相 */}
          <svg
            width="12"
            height="12"
            aria-hidden
            style={{ flexShrink: 0 }}
          >
            <rect
              x="0.5"
              y="0.5"
              width="11"
              height="11"
              rx="2.5"
              fill={it.color}
              stroke="var(--border-strong)"
              strokeWidth="0.75"
            />
            <rect
              x="1.5"
              y="1.5"
              width="9"
              height="9"
              rx="1.5"
              fill={`url(#${categoryPatternId(it.label)})`}
              color={it.color}
            />
          </svg>
          <span style={{ fontSize: "var(--text-sm)", flex: 1 }}>{it.label}</span>
          <span
            className="u-tabular"
            style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}
          >
            {it.value}
          </span>
        </div>
      ))}
    </div>
  );
}

/** 分段控件。role=tablist —— 所以必须支持左右方向键，
    键盘用户不该靠 Tab 在两个选项间来回跳。 */
export function Segmented({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: string | number; label: string }[];
  value: string | number;
  onChange: (v: string | number) => void;
  label: string;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    const dir = e.key === "ArrowRight" ? 1
      : e.key === "ArrowLeft" ? -1
      : 0;
    if (dir === 0) return;
    e.preventDefault();
    const i = options.findIndex((o) => o.value === value);
    // 到头就绕回，tablist 是个环
    const next = (i + dir + options.length) % options.length;
    onChange(options[next].value);
    /* 必须等重渲染完再对焦。
       onChange 触发后旧的 tab 会带着 tabIndex=-1 卸载、
       新的才挂上，此刻 refs.current[next] 还是 null ——
       实测焦点直接掉回了 body，键盘用户彻底失联。 */
    requestAnimationFrame(() => refs.current[next]?.focus());
  };

  return (
    <div
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      style={{
        display: "inline-flex",
        padding: 2,
        background: "var(--bg-sunken)",
        borderRadius: "var(--radius-md)",
        gap: 2,
      }}
    >
      {options.map((o, i) => {
        const active = o.value === value;
        return (
          <button
            key={String(o.value)}
            ref={(el) => { refs.current[i] = el; }}
            role="tab"
            aria-selected={active}
            /* tablist 里只有选中的那个能 Tab 进去，
               其余用方向键走 —— 这是 APG 的标准模式 */
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(o.value)}
            /* 26px 高的分段按钮太小，纵向扩到 40px */
            className="df-hit-v df-hit-v-4"
            style={{
              height: 26,
              padding: "0 12px",
              borderRadius: "var(--radius-sm)",
              background: active ? "var(--bg-surface)" : "transparent",
              color: active ? "var(--text-primary)" : "var(--text-tertiary)",
              fontSize: "var(--text-xs)",
              fontWeight: active
                ? "var(--weight-semibold)"
                : "var(--weight-normal)",
              boxShadow: active ? "var(--shadow-sm)" : "none",
              position: "relative",
              touchAction: "manipulation",
              transition: `background var(--dur-base) var(--ease-out),
                          color var(--dur-base) var(--ease-out)`,
            }}
          >
            {o.label}
            <FocusRing />
          </button>
        );
      })}
    </div>
  );
}
