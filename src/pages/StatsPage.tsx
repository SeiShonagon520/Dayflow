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
  categoryGlyph,
  categoryPatternId,
  categoryVar,
  formatMinutes,
  fullDate,
  scoreVar,
} from "@/lib/format";
import { Badge, Button, Card, ChartPopover, EmptyState, SectionTitle, SegmentedControl, Spinner } from "@/components/ui";
import { LineIcon } from "@/components/LineIcon";
import { LoadingHandoff } from "@/components/LoadingHandoff";
import { CategoryPatterns } from "@/components/CategoryPatterns";
import { useIsPhone } from "@/lib/useMediaQuery";

export function StatsPage({ active = true }: { active?: boolean }) {
  // 类别形状的 pattern 定义挂在页面根部，全页图表共用
  const patterns = <CategoryPatterns />;
  const [days, setDays] = useState<7 | 30>(7);
  const [data, setData] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  /* 重新取数（切周期）与首次加载是两种状态：
     前者保留旧内容压暗，后者才显示骨架。 */
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef(0);
  const hasData = useRef(false);

  const load = async (d: 7 | 30) => {
    const id = ++request.current;
    if (!hasData.current) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const next = await api.getStats(d);
      if (id === request.current) {
        hasData.current = true;
        setData(next);
      }
    } catch (e) {
      if (id === request.current) setError(e instanceof ApiError ? e.message : "加载失败");
    } finally {
      if (id === request.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  };

  useEffect(() => {
    if (!active) return;
    void load(days);
    return () => { request.current++; };
  }, [days, active]);

  // Hook 必须在所有 early return 之前调用。
  // 放在后面时，加载中的那一帧会少一个 hook，React 抛
  // "Rendered more hooks than during the previous render"，整页白掉。
  const phone = useIsPhone();

  const m = data?.metrics;
  const todayHours = m ? (m.todayMinutes ?? m.todayHours * 60) / 60 : 0;

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
          <span className="df-page-subtitle df-stats-period">
            <span className="df-stats-range" data-refreshing={refreshing || undefined}>
              {data && `${data.rangeStart} → ${data.rangeEnd}`}
            </span>
            <span role="status" className="df-stats-refresh">
              {refreshing ? "正在更新统计…" : ""}
            </span>
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

      <LoadingHandoff loading={loading}
        skeleton={<div className="df-wait"><Spinner />正在加载统计</div>}>
      {error && (!data || !m || m.activityCount === 0) ? (
        <EmptyState icon={<LineIcon name="alert" size={36} />} title="统计数据加载失败" description={error}
          action={<Button onClick={() => load(days)}>重试</Button>} />
      ) : !data || !m || m.activityCount === 0 ? (
        <EmptyState icon={<LineIcon name="chart" size={36} />} title={`最近 ${data?.days ?? days} 天没有活动记录`}
          description="开始记录后，这里会显示时间分布、专注趋势和应用使用排行。" />
      ) : (
      <div
        className="df-stats-container"
        aria-busy={refreshing || undefined}
      >
        {error && (
          <div className="df-inline-notice" role="alert">
            <span>更新失败，当前显示上一次读取的统计。</span>
            <Button size="sm" onClick={() => load(days)}>重试</Button>
          </div>
        )}

        {/* ── 今日目标条（精简横幅） ─────────────────── */}
        <Card className="df-goal-banner">
          <div className="df-goal-banner-head">
            <div className="df-goal-banner-title">
              <span className="df-goal-banner-label">今日目标</span>
              <span className="df-goal-banner-nums u-tabular">
                {formatMinutes(m.todayMinutes ?? m.todayHours * 60)}
                <span className="df-goal-banner-target"> / {data.dailyGoal || 8} 小时</span>
              </span>
            </div>
            <Badge tone={todayHours >= (data.dailyGoal || 8) ? "success" : "accent"} className="u-tabular">
              {Math.min(100, Math.round((todayHours / (data.dailyGoal || 8)) * 100))}%
            </Badge>
          </div>
          <div
            role="progressbar"
            aria-label="今日目标"
            aria-valuemin={0}
            aria-valuemax={data.dailyGoal || 8}
            aria-valuenow={Math.min(todayHours, data.dailyGoal || 8)}
            className="df-goal-track"
          >
            <div className="df-fill" style={{
              background: todayHours >= (data.dailyGoal || 8) ? "var(--success)" : "var(--accent)",
              transform: `scaleX(${Math.min(1, todayHours / (data.dailyGoal || 8))})`,
            }} />
          </div>
        </Card>

        {/* ── 4 枚核心 KPI 指标卡（宽屏 4 列 / 中屏 2×2 / 窄屏 1 列） ── */}
        <div className="df-kpi-grid">
          <Metric
            label="总时长"
            value={formatMinutes(m.totalMinutes ?? m.totalHours * 60)}
            unit=""
            change={data.changes.totalHours}
            color="var(--cat-work)"
          />
          <Metric
            label="平均生产力"
            value={m.avgScore > 0 ? `${m.avgScore}` : "暂无评分"}
            unit={m.avgScore > 0 ? "分" : ""}
            change={m.avgScore > 0 ? data.changes.avgScore : 0}
            color={m.avgScore > 0 ? `var(${scoreVar(m.avgScore)})` : "var(--text-tertiary)"}
          />
          <Metric
            label="深度工作"
            value={formatMinutes(m.deepWorkMinutes ?? 0)}
            unit=""
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
        <div className="df-chart-grid-a df-chart-row">
          <Card>
            <SectionTitle action={<span className="df-section-meta">按累计时长</span>}>类别分布</SectionTitle>
            <Donut data={data.categories} total={m.totalHours * 60} />
          </Card>

          <Card>
            <SectionTitle action={<span className="df-section-meta">悬停查看明细</span>}>生产力趋势</SectionTitle>
            <Trend data={data.trend} />
          </Card>
        </div>

        {/* ── 贡献日历 + 时段分布 ────────────────── */}
        <div className="df-chart-grid-b df-chart-row">
          <Card>
            <SectionTitle action={<span className="df-section-meta">每日投入热力</span>}>每日投入</SectionTitle>
            <Calendar data={data.calendar} />
          </Card>

          <Card>
            <SectionTitle action={<span className="df-section-meta">00:00 – 23:59</span>}>时段分布</SectionTitle>
            <Hourly data={data.hourly} />
          </Card>
        </div>

        {/* ── 应用排行 ────────────────────────────── */}
        <Card>
          <SectionTitle action={<span className="df-section-meta">Top 10</span>}>应用使用排行</SectionTitle>
          <AppRanking data={data.appRanking} />
        </Card>
      </div>
      )}
      </LoadingHandoff>
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
          key={value}
          className="df-value-change u-tabular"
          style={{ fontSize: "var(--text-2xl)", fontWeight: "var(--weight-semibold)" }}
        >
          {value}
        </span>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--text-tertiary)" }}>
          {unit}
        </span>
      </div>

      {change !== undefined && Math.abs(change) > 0.1 && (
        <div style={{ marginTop: 8 }}>
          <Badge tone={up ? "success" : "danger"} className="df-value-change u-tabular">
            {up ? "↑" : "↓"} {Math.abs(change).toFixed(0)}% 较上一周期
          </Badge>
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
  const [hovered, setHovered] = useState<string | null>(null);
  const size = 168;
  const stroke = 22;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;

  let offset = 0;
  const arcs = data.map((d) => {
    const frac = total > 0 ? d.minutes / total : 0;
    const arc = { ...d, frac, dash: frac * c, offset };
    offset += frac * c;
    return arc;
  });

  const activeArc = hovered ? arcs.find((a) => a.name === hovered) ?? null : null;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-5)",
        flexWrap: "wrap",
      }}
      onMouseLeave={() => setHovered(null)}
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
          {arcs.map((a) => {
            const dimmed = hovered !== null && hovered !== a.name;
            return (
              <circle
                key={a.name}
                className="df-donut-arc"
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                stroke={`var(${categoryVar(a.name)})`}
                strokeWidth={stroke}
                strokeDasharray={`${a.dash} ${c - a.dash}`}
                strokeDashoffset={-a.offset}
                transform={`rotate(-90 ${size / 2} ${size / 2})`}
                style={{ opacity: dimmed ? 0.3 : 1 }}
                onMouseEnter={() => setHovered(a.name)}
              />
            );
          })}
        </svg>
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
          }}
        >
          <span
            className="u-tabular"
            style={{ fontSize: "var(--text-md)", fontWeight: "var(--weight-semibold)" }}
          >
            {activeArc ? formatMinutes(activeArc.minutes) : data.length}
          </span>
          <span style={{ fontSize: "var(--text-2xs)", color: "var(--text-tertiary)" }}>
            {activeArc
              ? `${categoryGlyph(activeArc.name)} ${activeArc.name} · ${Math.round(activeArc.frac * 100)}%`
              : "个类别"}
          </span>
        </div>
      </div>

      <Legend
        hovered={hovered}
        onHover={setHovered}
        items={data.map((d) => ({
          label: d.name,
          value: formatMinutes(d.minutes),
          color: `var(${categoryVar(d.name)})`,
        }))}
      />
    </div>
  );
}

// ── 趋势折线 ──────────────────────────────────────────────────

function chartAnchor(element: Element) {
  const chart = element.closest(".df-chart-wrap")!.getBoundingClientRect();
  const point = element.getBoundingClientRect();
  return { xPct: (point.left + point.width / 2 - chart.left) / chart.width * 100, yPx: point.top - chart.top };
}

function Trend({ data }: { data: { date: string; score: number; hours: number }[] }) {
  const [hovered, setHovered] = useState<({ index: number } & ReturnType<typeof chartAnchor>) | null>(null);
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

  const activeDatum = hovered ? data[hovered.index] : null;

  return (
    <div className="df-chart-wrap" onMouseLeave={() => setHovered(null)}>
      {activeDatum && hovered && (
        <ChartPopover
          xPct={hovered.xPct}
          yPx={hovered.yPx}
          title={fullDate(activeDatum.date)}
          value={`${activeDatum.score} 分`}
          meta={`${activeDatum.hours} 小时`}
          color={`var(${scoreVar(activeDatum.score)})`}
        />
      )}
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
                  <g
                    key={data[i].date}
                    onMouseEnter={(event) => setHovered({ index: i, ...chartAnchor(event.currentTarget) })}
                    onFocus={(event) => setHovered({ index: i, ...chartAnchor(event.currentTarget) })}
                    onBlur={() => setHovered(null)}
                    tabIndex={0}
                    role="button"
                    aria-label={`${data[i].date}，${data[i].score} 分，${data[i].hours} 小时`}
                    style={{ cursor: "pointer" }}
                  >
                    <circle cx={x} cy={y} r={10} fill="transparent" />
                    <circle
                      cx={x}
                      cy={y}
                      r={hovered?.index === i ? 4 : 3}
                      fill="var(--accent)"
                      stroke="var(--bg-surface)"
                      strokeWidth={1.5}
                    />
                  </g>
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
  const [hovered, setHovered] = useState<({ index: number } & ReturnType<typeof chartAnchor>) | null>(null);
  const cell = 13;
  const gap = 3;
  const weeks = Math.max(1, Math.ceil(data.length / 7));
  const maxH = Math.max(1, ...data.map((d) => d.hours));

  const opacityOf = (hours: number) => {
    if (hours <= 0) return 0;
    const f = hours / maxH;
    // 用 4 档离散透明度兼容 Chromium 105+，在小方块上也更易分辨
    if (f <= 0.25) return 0.28;
    if (f <= 0.5) return 0.52;
    if (f <= 0.75) return 0.76;
    return 1;
  };

  const activeDay = hovered !== null ? data[hovered.index] : null;

  return (
    <div className="df-chart-wrap" onMouseLeave={() => setHovered(null)}>
      {activeDay && hovered && (
        <ChartPopover
          xPct={hovered.xPct}
          yPx={hovered.yPx}
          title={fullDate(activeDay.date)}
          value={`${activeDay.hours} 小时`}
          meta={`${activeDay.score} 分 · ${activeDay.count} 条活动`}
          color="var(--success)"
        />
      )}
      <div
        onScroll={() => setHovered(null)}
        style={{
          display: "grid",
          gridTemplateRows: `repeat(7, ${cell}px)`,
          gridAutoFlow: "column",
          gap,
          overflowX: "auto",
        }}
      >
        {data.map((d, idx) => {
          const alpha = opacityOf(d.hours);
          return (
            <button
              key={d.date}
              type="button"
              className="df-cal-cell"
              aria-label={`${fullDate(d.date)}，${d.hours} 小时，${d.score} 分，${d.count} 条活动`}
              onMouseEnter={(event) => setHovered({ index: idx, ...chartAnchor(event.currentTarget) })}
              onFocus={(event) => setHovered({ index: idx, ...chartAnchor(event.currentTarget) })}
              onBlur={() => setHovered(null)}
              style={{
                width: cell,
                height: cell,
                borderRadius: 3,
                background: "var(--bg-sunken)",
                overflow: "hidden",
                padding: 0,
              }}
            >
              {alpha > 0 && (
                <div
                  style={{
                    width: "100%",
                    height: "100%",
                    background: "var(--success)",
                    opacity: alpha,
                  }}
                />
              )}
            </button>
          );
        })}
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
        {[0, 0.28, 0.52, 0.76, 1].map((alpha) => (
          <div
            key={alpha}
            style={{
              width: 10,
              height: 10,
              borderRadius: 2,
              background: "var(--bg-sunken)",
              overflow: "hidden",
            }}
          >
            {alpha > 0 && (
              <div
                style={{
                  width: "100%",
                  height: "100%",
                  background: "var(--success)",
                  opacity: alpha,
                }}
              />
            )}
          </div>
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
  const [hoveredHour, setHoveredHour] = useState<number | null>(null);
  const maxMin = Math.max(1, ...data.map((h) =>
    h.reduce((s, x) => s + x.minutes, 0)
  ));
  const hoveredMins = hoveredHour !== null && data[hoveredHour]
    ? data[hoveredHour].reduce((s, x) => s + x.minutes, 0)
    : 0;

  return (
    <div className="df-chart-wrap" onMouseLeave={() => setHoveredHour(null)}>
      {hoveredHour !== null && (
        <ChartPopover
          xPct={((hoveredHour + 0.5) / Math.max(1, data.length)) * 100}
          yPx={32}
          title={`${String(hoveredHour).padStart(2, "0")}:00 – ${String(hoveredHour).padStart(2, "0")}:59`}
          value={hoveredMins > 0 ? formatMinutes(hoveredMins) : "无记录"}
          color="var(--accent)"
        />
      )}
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
          // 纯 GPU scaleY 缩放（零 height 重排）
          const ratio = mins > 0 ? Math.max(0.06, mins / maxMin) : 0.04;
          const active = hoveredHour === hi;
          return (
            <button
              key={hi}
              type="button"
              aria-label={`${hi}:00，${formatMinutes(mins)}`}
              onMouseEnter={() => setHoveredHour(hi)}
              onFocus={() => setHoveredHour(hi)}
              onBlur={() => setHoveredHour(null)}
              style={{
                display: "flex",
                flexDirection: "column",
                justifyContent: "flex-end",
                height: 76,
                padding: 0,
              }}
            >
              <div
                className="df-hourly-bar"
                style={{
                  transform: `scaleY(${ratio})`,
                  background: mins > 0 ? "var(--accent)" : "var(--bg-sunken)",
                  opacity: active ? 1 : mins > 0 ? 0.4 + (mins / maxMin) * 0.6 : 1,
                }}
              />
            </button>
          );
        })}
      </div>
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
            <div className="df-fill"
              style={{
                transform: `scaleX(${d.minutes / max})`,
                background: "var(--accent)",
                borderRadius: "var(--radius-full)",
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
  hovered,
  onHover,
}: {
  items: { label: string; value: string; color: string }[];
  hovered?: string | null;
  onHover?: (label: string | null) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, minWidth: 140 }}>
      {items.map((it) => {
        const dimmed = hovered != null && hovered !== it.label;
        return (
          <div
            key={it.label}
            className="df-legend-row"
            style={{ opacity: dimmed ? 0.45 : 1 }}
            onMouseEnter={() => onHover?.(it.label)}
            onMouseLeave={() => onHover?.(null)}
          >
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
        );
      })}
    </div>
  );
}

/** 分段控件：复用统一滑动胶囊 SegmentedControl */
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
  return (
    <SegmentedControl
      roleMode="tablist"
      compact
      options={options}
      value={value}
      onChange={onChange}
      label={label}
    />
  );
}
