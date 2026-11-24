/*
 * 时间轴页面
 *
 * 旧界面的问题：每张卡片是一个大圆角容器，容器里再套标签、摘要、应用，
 * 层层描边，20 张卡片滚下去就是一堵墙。视觉重量全部一样，
 * 扫一眼分不出哪条重要。
 *
 * 这里的做法：
 *   · 取消卡片容器，靠留白和一条细时间轴区分条目
 *   · 层级靠字号和字重：标题 > 摘要 > 元信息
 *   · 类别色只出现在一个 8px 的竖条上，不给整张卡上色
 *   · 生产力分数用「色点 + 数字 + 文字」三重表达，不只靠颜色
 */

import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useRecording } from "@/lib/useRecording";
import { ActivityCard, ApiError, api } from "@/lib/api";
import {
  categoryGlyph,
  categoryVar,
  formatClock,
  formatMinutes,
  isToday,
  prettyDate,
  scoreLabel,
  scoreVar,
  shiftDate,
  todayStr,
  fullDate,
} from "@/lib/format";
import { Badge, Button, EmptyState } from "@/components/ui";
import { useIsPhone } from "@/lib/useMediaQuery";
import { useLatest } from "@/lib/useLatest";
import { useExit } from "@/lib/motion";
import { Dialog } from "@/components/Dialog";
import { LoadingHandoff } from "@/components/LoadingHandoff";
import { FocusRing } from "@/components/FocusRing";

const EMPTY_CARDS: ActivityCard[] = [];

export function TimelinePage({
  date,
  onDateChange,
  onOpenReports,
  active,
  recordingControl,
}: {
  date: string;
  onDateChange: (d: string) => void;
  onOpenReports: () => void;
  active: boolean;
  recordingControl: ReturnType<typeof useRecording>;
}) {
  const [allCards, setCards] = useState<ActivityCard[]>([]);
  const [loadedDate, setLoadedDate] = useState<string | null>(null);
  const cards = loadedDate === date ? allCards : EMPTY_CARDS;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const currentDate = useLatest(date);
  const [editing, setEditing] = useState<ActivityCard | null>(null);
  const [toast, setToast] = useState<{ card: ActivityCard; date: string }[]>([]);
  const [undoBusy, setUndoBusy] = useState(false);
  const [undoFailed, setUndoFailed] = useState(false);
  const toastTimer = useRef<number | null>(null);
  const [toastClosing, setToastClosing] = useState(false);
  const toastElement = useRef<HTMLDivElement>(null);
  const [editClosing, setEditClosing] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");
  const request = useRef(0);
  const mutating = useRef(0);
  const UNDO_MS = 10000;

  useExit(toastElement, toastClosing, () => {
    setToast([]);
    setToastClosing(false);
  });

  const closeEdit = () => setEditClosing(true);

  useEffect(() => () => {
    request.current++;
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
  }, []);

  const load = async (d: string, quiet = false) => {
    if (d !== currentDate.current || (quiet && mutating.current)) return;
    const id = ++request.current;
    if (!quiet) setLoading(true);
    if (!quiet) setError(null);
    try {
      const res = await api.getCards(d);
      /* 后端少返回一个字段就整页崩溃没有意义。
         日报页已经栽过一次同样的跟头。 */
      if (id !== request.current || (quiet && mutating.current)) return;
      setError(null);
      const next = Array.isArray(res?.cards) ? res.cards : [];
      setCards((previous) => quiet && JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
      setFilter((current) => current && !next.some((card) => (card.category || "其他") === current) ? null : current);
    } catch (e) {
      if (id !== request.current || quiet) return;
      setError(e instanceof ApiError ? e.message : "加载失败");
      setCards([]);
    } finally {
      if (!quiet && id === request.current) {
        setLoadedDate(d);
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    load(date);
    return () => { request.current++; };
  }, [date]);

  useEffect(() => {
    if (!active || loadedDate !== date || date !== todayStr()) return;
    const timer = window.setInterval(() => { if (!document.hidden) void load(date, true); }, 8000);
    return () => window.clearInterval(timer);
  }, [active, loadedDate, date]);

  // 分类计数
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of cards) m.set(c.category || "其他", (m.get(c.category || "其他") ?? 0) + 1);
    return m;
  }, [cards]);

  const visible = useMemo(() => {
    let list = cards;
    if (filter) list = list.filter((c) => (c.category || "其他") === filter);
    if (deferredQuery.trim()) {
      const q = deferredQuery.trim().toLowerCase();
      list = list.filter(
        (c) =>
          c.title.toLowerCase().includes(q) ||
          c.summary.toLowerCase().includes(q) ||
          (c.category || "").toLowerCase().includes(q)
      );
    }
    return [...list].sort((a, b) =>
      (a.startTime ?? "").localeCompare(b.startTime ?? "")
    );
  }, [cards, filter, deferredQuery]);

  const totals = useMemo(() => {
    const mins = cards.reduce((s, c) => s + c.durationMinutes, 0);
    return { count: cards.length, minutes: mins };
  }, [cards]);

  const handleDelete = async (card: ActivityCard) => {
    setOperationError(null);
    mutating.current++;
    setCards((cs) => cs.filter((c) => c.id !== card.id));
    try {
      await api.deleteCard(card.id);
      setToast((items) => [...items, { card, date }]);
      setToastClosing(false);
      setUndoFailed(false);
      if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
      toastTimer.current = window.setTimeout(() => setToastClosing(true), UNDO_MS);
    } catch (e) {
      if (date !== currentDate.current) return;
      setCards((current) => current.some((item) => item.id === card.id)
        ? current : [...current, card]);
      setOperationError(e instanceof ApiError ? e.message : "删除失败，活动已恢复");
    } finally {
      mutating.current--;
    }
  };

  const handleUndo = async () => {
    if (!toast.length || undoBusy) return;
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    setUndoBusy(true);
    setUndoFailed(false);
    setToastClosing(false);
    mutating.current++;
    const failed = new Set<number>();
    try {
      for (const { card, date: deletedOn } of toast) {
        try {
          await api.restoreCard(card);
          if (deletedOn === currentDate.current) {
            setCards((items) => items.some((item) => item.id === card.id) ? items : [...items, card]);
          }
        } catch {
          failed.add(card.id);
        }
      }
      const attempted = new Set(toast.map(({ card }) => card.id));
      setToast((items) => items.filter(({ card }) => !attempted.has(card.id) || failed.has(card.id)));
      setUndoFailed(failed.size > 0);
      if (failed.size && toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    } finally {
      mutating.current--;
      setUndoBusy(false);
    }
  };

  const handleSave = async (card: ActivityCard) => {
    setEditError("");
    setEditSaving(true);
    mutating.current++;
    try {
      await api.updateCard(card.id, card);
      if (date === currentDate.current) {
        setCards((items) => items.map((item) => item.id === card.id ? { ...item, ...card } : item));
      }
      closeEdit();
    } catch (e) {
      setEditError(e instanceof ApiError ? e.message : "保存失败，请重试");
    } finally {
      mutating.current--;
      setEditSaving(false);
    }
  };

  const phone = useIsPhone();

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* ── 工具栏 ───────────────────────────────────────
          窄屏改成两行：第一行日期导航，第二行搜索 + 统计。
          四件事挤在一行时，320px 下搜索框直接被推出屏幕，
          实测右边界 429px > 视口 320px。 */}
      <div
        className="df-toolbar"
        data-stacked={phone ? "true" : "false"}
      >
        <div className="df-toolbar-row">
          <div className="df-datenav">
            <IconButton
              label="前一天"
              onClick={() => onDateChange(shiftDate(date, -1))}
            >
              ‹
            </IconButton>
            <div className="df-datelabel">
              <div key={date} className="df-value-change" style={{
                fontSize: "var(--text-md)",
                fontWeight: "var(--weight-semibold)",
              }}>
                {isToday(date) ? "今天" : prettyDate(date)}
                {isToday(date) && (
                  <span
                    style={{
                      fontSize: "var(--text-2xs)",
                      color: "var(--text-tertiary)",
                      fontWeight: "var(--weight-normal)",
                      marginLeft: 6,
                    }}
                  >
                    {fullDate(date)}
                  </span>
                )}
              </div>
            </div>
            <IconButton
              label="后一天"
              onClick={() => onDateChange(shiftDate(date, 1))}
              disabled={date >= todayStr()}
            >
              ›
            </IconButton>
          </div>

          {!isToday(date) && (
            <Button size="sm" variant="ghost" onClick={() => onDateChange(todayStr())}>
              回到今天
            </Button>
          )}

          <div className="df-toolbar-spacer" />

          {totals.count > 0 && !phone && (
            <span
              className="u-tabular df-toolbar-count"
              style={{
                fontSize: "var(--text-xs)",
                color: "var(--text-tertiary)",
              }}
            >
              {totals.count} 项 · {formatMinutes(totals.minutes)}
            </span>
          )}
          <Button size="sm" onClick={onOpenReports}>
            日报
          </Button>
        </div>

        {/* 搜索在第二行，窄屏时占满宽度 */}
        <div className="df-toolbar-row df-toolbar-search">
          <SearchBox value={query} onChange={setQuery} full={phone} />
          {phone && totals.count > 0 && (
            <span
              className="u-tabular"
              style={{
                fontSize: "var(--text-xs)",
                color: "var(--text-tertiary)",
                whiteSpace: "nowrap",
              }}
            >
              {totals.count} 项 · {formatMinutes(totals.minutes)}
            </span>
          )}
        </div>
      </div>

      {/* ── 分类筛选 ───────────────────────────────────── */}
      {cards.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: "var(--space-2)",
            padding: "var(--space-3) var(--space-6)",
            borderBottom: "1px solid var(--border-subtle)",
            overflowX: "auto",
            flexShrink: 0,
          }}
        >
          <FilterPill
            label="全部"
            count={cards.length}
            active={filter === null}
            onClick={() => setFilter(null)}
          />
          {[...counts.entries()]
            .sort((a, b) => b[1] - a[1])
            .map(([cat, n]) => (
              <FilterPill
                key={cat}
                label={cat}
                count={n}
                color={categoryVar(cat)}
                active={filter === cat}
                onClick={() => setFilter(filter === cat ? null : cat)}
              />
            ))}
        </div>
      )}

      {operationError && (
        <div className="df-inline-notice df-feedback" role="alert">
          <span>{operationError}</span>
          <Button size="sm" variant="ghost" onClick={() => setOperationError(null)}>关闭</Button>
        </div>
      )}

      {/* ── 列表 ───────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: "auto", position: "relative" }}>
        <LoadingHandoff
          loading={loading || loadedDate !== date}
          skeleton={
            /* 骨架屏而不是一个孤立的小转圈。
               转圈只说「在加载」，骨架屏顺带把版式先摆出来 ——
               加载完时内容不会跳位。 */
            <div
              style={{
                padding: "var(--space-4) var(--space-6)",
                display: "flex",
                flexDirection: "column",
                gap: "var(--space-4)",
              }}
              aria-busy="true"
              aria-label="正在加载活动记录"
            >
              {[0, 1, 2, 3].map((i) => (
                <div key={i} style={{ display: "flex", gap: "var(--space-4)" }}>
                  <div
                    className="df-skeleton"
                    style={{ width: 92, height: 14, flexShrink: 0 }}
                  />
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
                    <div
                      className="df-skeleton"
                      style={{ width: `${58 + ((i * 11) % 26)}%`, height: 15 }}
                    />
                    <div
                      className="df-skeleton"
                      style={{ width: `${78 + ((i * 7) % 18)}%`, height: 12 }}
                    />
                  </div>
                </div>
              ))}
            </div>
          }
        >
        {error ? (
          <EmptyState
            icon="⚠️"
            title="加载失败"
            description={error}
            action={<Button onClick={() => load(date)}>重试</Button>}
          />
        ) : visible.length === 0 ? (
          <EmptyStateForTimeline
            isToday={isToday(date)}
            isFiltered={!!filter || !!query}
            recordingControl={recordingControl}
            onClearFilter={() => {
              setFilter(null);
              setQuery("");
            }}
          />
        ) : (
          <div className="df-row-list" data-long={visible.length > 100 || undefined}>
            {visible.map((card) => (
              <ActivityRow
                key={card.id}
                card={card}
                onEdit={() => {
                  setEditClosing(false);
                  setEditError("");
                  setEditing(card);
                }}
                onDelete={() => handleDelete(card)}
              />
            ))}
          </div>
        )}
        </LoadingHandoff>
      </div>

      {editing && (
        <EditDialog
          card={editing}
          open={!editClosing}
          onClose={() => { if (!editSaving) closeEdit(); }}
          saving={editSaving}
          error={editError}
          onExited={() => setEditing(null)}
          onSave={handleSave}
        />
      )}

      {toast.length > 0 && createPortal(
        <div
          ref={toastElement}
          data-closing={toastClosing || undefined}
          role="status"
          aria-live="polite"
          style={{
            position: "fixed",
            left: "50%",
            translate: "-50% 0",
            display: "flex",
            alignItems: "center",
            gap: "var(--space-4)",
            padding: "var(--space-3) var(--space-4)",
            paddingBottom: "calc(var(--space-3) + 3px)",
            background: "var(--bg-raised)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-popover)",
            zIndex: "var(--z-toast)",
            overflow: "hidden",
          }}
          className="df-toast df-undo-toast"
        >
          <span style={{ fontSize: "var(--text-sm)" }}>
            {undoFailed ? "部分活动未能恢复，可以重试" : toast.length === 1
              ? `已删除「${truncate(toast[0].card.title, 18)}」`
              : `已删除 ${toast.length} 条活动`}
          </span>
          <Button size="sm" variant="ghost" onClick={handleUndo} loading={undoBusy} disabled={toastClosing}>
            撤销
          </Button>
          {!undoBusy && !undoFailed && <span
            key={toast[toast.length - 1]?.card.id}
            aria-hidden
            className="df-undo-timer"
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: 0,
              height: 2,
            }}
          />}
        </div>, document.body
      )}
    </div>
  );
}

// ── 单条活动 ──────────────────────────────────────────────

function ActivityRow({
  card,
  onEdit,
  onDelete,
}: {
  card: ActivityCard;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const score = card.productivityScore;
  const apps = card.appSites.slice(0, 3);

  return (
    <div className="df-row">
      {/* 时间列：固定宽度，让所有条目的时间戳垂直对齐 */}
      <div className="df-row-time">
        <div style={{ color: "var(--text-secondary)" }}>
          {formatClock(card.startTime)}
        </div>
        <div style={{ marginTop: 1 }}>{formatMinutes(card.durationMinutes)}</div>
      </div>

      {/* 分类色节点落在贯穿列表的品牌蓝轨迹上。 */}
      <div
        aria-hidden
        className="df-row-node"
        style={{ background: `var(${categoryVar(card.category)})` }}
      />

      {/* 主体 */}
      <div className="df-row-body">
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: "var(--space-2)",
            flexWrap: "wrap",
          }}
        >
          <h4
            style={{
              fontSize: "var(--text-md)",
              fontWeight: "var(--weight-semibold)",
              color: "var(--text-primary)",
            }}
          >
            {card.title || "未命名活动"}
          </h4>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontSize: "var(--text-xs)",
              color: "var(--text-tertiary)",
            }}
          >
            {/* 类别形状：色盲下靠它区分，不靠色相 */}
            <span
              aria-hidden
              style={{
                color: `var(${categoryVar(card.category)})`,
                fontSize: "var(--text-2xs)",
                lineHeight: 1,
              }}
            >
              {categoryGlyph(card.category)}
            </span>
            {card.category}
          </span>

          {card.durationMinutes >= 60 && (
            <Badge tone="accent">深度工作</Badge>
          )}

          {score > 0 && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                marginLeft: "auto",
                fontSize: "var(--text-xs)",
                color: `var(${scoreVar(score)})`,
                fontVariantNumeric: "tabular-nums",
              }}
              /* 色点 + 数字 + 文字：三重表达，不只靠颜色 */
              title={`生产力 ${scoreLabel(score)}`}
            >
              <span
                aria-hidden
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: `var(${scoreVar(score)})`,
                }}
              />
              {Math.round(score)}%
              <span style={{ color: "var(--text-tertiary)" }}>{scoreLabel(score)}</span>
            </span>
          )}
        </div>

        {card.summary && (
          <p
            className="u-line-clamp-2"
            style={{
              marginTop: 3,
              fontSize: "var(--text-sm)",
              color: "var(--text-secondary)",
              lineHeight: "var(--leading-normal)",
            }}
          >
            {card.summary}
          </p>
        )}

        {apps.length > 0 && (
          <div
            style={{
              display: "flex",
              gap: "var(--space-2)",
              marginTop: 6,
              flexWrap: "wrap",
            }}
          >
            {apps.map((a) => (
              <span
                key={a.name}
                style={{
                  fontSize: "var(--text-2xs)",
                  color: "var(--text-tertiary)",
                  background: "var(--bg-sunken)",
                  padding: "1px 6px",
                  borderRadius: "var(--radius-xs)",
                }}
              >
                {a.name}
              </span>
            ))}
            {card.appSites.length > 3 && (
              <span style={{ fontSize: "var(--text-2xs)", color: "var(--text-placeholder)" }}>
                +{card.appSites.length - 3}
              </span>
            )}
          </div>
        )}
      </div>

      {/* 操作：悬停/聚焦才出现，但始终可 Tab 到。
          触屏没有 hover —— df-hover-only 在 (hover: none) 下强制显形，
          否则编辑和删除在手机上等于不存在。

          窄屏下图标替代文字：两个 28px 的文字按钮会占掉近一半宽度。 */}
      <div className="df-hover-only df-row-actions">
        <Button size="sm" variant="ghost" onClick={onEdit} title="编辑" aria-label="编辑">
          <span className="df-actions-label">编辑</span>
          <span className="df-actions-icon" aria-hidden>✎</span>
        </Button>
        <Button size="sm" variant="ghost" onClick={onDelete} title="删除" aria-label="删除">
          <span className="df-actions-label">删除</span>
          <span className="df-actions-icon" aria-hidden>✕</span>
        </Button>
      </div>
    </div>
  );
}

// ── 子组件 ────────────────────────────────────────────────

function IconButton({
  children,
  onClick,
  label,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      /* 28×28 的按钮很难点中。伪元素纵向扩到 42px；
         横向不扩 —— 前一天/后一天中心距只有 32px，
         各自横扩到 40px 会互相盖住对方的点击区。
         横向 28px 本身已过 24px 的底线。 */
      className="df-hit-v"
      style={{
        width: 28,
        height: 28,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: "var(--radius-md)",
        color: "var(--text-secondary)",
        fontSize: "var(--text-lg)",
        lineHeight: 1,
        opacity: disabled ? 0.35 : 1,
        position: "relative",
        touchAction: "manipulation",
        transition: `background var(--dur-base) var(--ease-out)`,
      }}
      onMouseEnter={(e) => {
        if (!disabled) e.currentTarget.style.background = "var(--bg-hover)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
      }}
    >
      {children}
      <FocusRing />
    </button>
  );
}

function FilterPill({
  label,
  count,
  active,
  onClick,
  color,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
  color?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      /* 28px 高的药丸命中区偏小，纵向扩到 40px。
         药丸之间横向有 8px 间隙且各自 70px 宽，
         纵向扩展不会碰到邻居。 */
      className="df-hit-v"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        height: 28,
        padding: "0 10px",
        borderRadius: "var(--radius-full)",
        background: active ? "var(--accent-subtle)" : "transparent",
        border: "1px solid",
        borderColor: active ? "var(--accent)" : "var(--border-subtle)",
        color: active ? "var(--accent)" : "var(--text-secondary)",
        fontSize: "var(--text-xs)",
        fontWeight: active ? "var(--weight-semibold)" : "var(--weight-normal)",
        whiteSpace: "nowrap",
        flexShrink: 0,
        position: "relative",
        touchAction: "manipulation",
        transition: `background var(--dur-base) var(--ease-out),
                    color var(--dur-base) var(--ease-out),
                    border-color var(--dur-base) var(--ease-out)`,
      }}
    >
      {/* 颜色 + 形状双重编码：色盲下靠形状区分 */}
      {color && (
        <span
          aria-hidden
          style={{
            color: `var(${color})`,
            fontSize: "var(--text-2xs)",
            lineHeight: 1,
          }}
        >
          {categoryGlyph(label)}
        </span>
      )}
      {label}
      <span className="u-tabular" style={{ color: "var(--text-tertiary)" }}>
        {count}
      </span>
      <FocusRing />
    </button>
  );
}

function SearchBox({
  value,
  onChange,
  full,
}: {
  value: string;
  onChange: (v: string) => void;
  full?: boolean;
}) {
  return (
    /* 这里不能靠伪元素扩命中区：::before 不是真元素，
       点在它上面命中的是包裹层 div，不是 input。
       实测「189×30」就是这么来的 —— 包装层扩了，输入框没扩。
       只能把输入框本身做高。 */
    <div
      style={{
        position: "relative",
        flex: full ? 1 : undefined,
      }}
    >
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="搜索活动"
        aria-label="搜索活动标题、摘要或类别"
        className="df-search"
        data-full={full ? "true" : "false"}
        style={{
          /* 34px，和其它输入框一致。比 40 小一点，
             但搜索框在工具栏里，旁边就是别的控件。 */
          height: 34,
          /* 聚焦时不改变宽度 —— 变宽会把右侧内容推出视口，
             这正是窄屏下溢出的原因。改用边框+环表达聚焦。 */
          width: "100%",
          maxWidth: full ? "none" : 240,
          padding: "0 var(--space-3) 0 28px",
          background: "var(--bg-surface)",
          /* border 和 color 走 .df-search —— 内联的 border 简写会
             整体覆盖 :focus-visible 的 border-color，实测聚焦时
             边框不变色，只剩 box-shadow 那一层环。 */
          borderRadius: "var(--radius-md)",
        }}
      />
      <span
        aria-hidden
        style={{
          position: "absolute",
          left: 10,
          top: "50%",
          transform: "translateY(-50%)",
          color: "var(--text-placeholder)",
          fontSize: "var(--text-sm)",
          pointerEvents: "none",
        }}
      >
        ⌕
      </span>
    </div>
  );
}

function EmptyStateForTimeline({
  isToday, isFiltered, recordingControl, onClearFilter,
}: {
  isToday: boolean;
  isFiltered: boolean;
  recordingControl: ReturnType<typeof useRecording>;
  onClearFilter: () => void;
}) {
  const { state, pending, run } = recordingControl;
  if (isFiltered) {
    return <EmptyState icon="⌕" title="没有匹配的活动"
      description="换个关键词，或查看全部记录。"
      action={<Button onClick={onClearFilter}>清除筛选</Button>} />;
  }
  if (!isToday) {
    return <EmptyState icon="📭" title="这一天没有活动记录"
      description="可以在上方选另一天，或回到今天。" />;
  }
  if (state?.isRecording) {
    const paused = state.isPaused || state.isIdlePaused;
    return <EmptyState icon="⏱" title={paused ? "录制已暂停" : "正在整理今天的活动"}
      description={paused ? "继续录制后，新的活动会陆续出现。" : "分析完成后，记录会自动显示在这里。"}
      action={paused && <Button variant="primary" loading={pending === "resume"}
        onClick={() => run("resume")}>继续录制</Button>} />;
  }
  return <EmptyState icon="⏱" title="今天还没有活动记录"
    description={state?.needsSetup ? "连接分析模型后，就可以开始自动整理活动。" : "录制开始后，活动会自动整理在这里。"}
    action={<Button variant="primary" loading={pending === "start"} onClick={() => run("start")}>
      {state?.needsSetup ? "连接分析模型" : "开始录制"}
    </Button>} />;
}

// ── 编辑对话框 ────────────────────────────────────────────

function EditDialog({
  card,
  open,
  onClose,
  onExited,
  onSave,
  saving,
  error,
}: {
  card: ActivityCard;
  open: boolean;
  onClose: () => void;
  onExited: () => void;
  onSave: (c: ActivityCard) => void;
  saving: boolean;
  error: string;
}) {
  const [title, setTitle] = useState(card.title);
  const [summary, setSummary] = useState(card.summary);
  const [category, setCategory] = useState(card.category);
  const [score, setScore] = useState(Math.round(card.productivityScore));

  /* Esc 和焦点循环都由 Dialog 统一处理，这里不要重复监听 ——
     两个 handler 都会跑，onClose 会被调两次。 */

  return (
    <Dialog open={open} onClose={onClose} onExited={onExited} labelledBy="editDialogTitle">
        <h3 id="editDialogTitle">编辑活动</h3>
        <fieldset disabled={saving} className="df-edit-fields">

        <label style={labelStyle}>
          标题
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            style={inputStyle}
          />
        </label>

        <label style={labelStyle}>
          类别
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            style={inputStyle}
          >
            {["工作", "编程", "学习", "会议", "娱乐", "社交", "休息", "其他"].map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>

        <label style={labelStyle}>
          生产力评分：{score}
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={score}
            onChange={(e) => setScore(Number(e.target.value))}
            style={{ accentColor: "var(--accent)" }}
          />
        </label>

        <label style={labelStyle}>
          摘要
          <textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            rows={3}
            style={{ ...inputStyle, height: "auto", padding: 8, resize: "vertical" }}
          />
        </label>

        </fieldset>
        {error && <p role="alert" style={{ color: "var(--danger)" }}>{error}</p>}
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: "var(--space-2)",
          }}
        >
          <Button onClick={onClose} disabled={saving}>取消</Button>
          <Button
            variant="primary" loading={saving} disabled={!title.trim()}
            onClick={() =>
              onSave({ ...card, title, summary, category, productivityScore: score })
            }
          >
            保存
          </Button>
        </div>
    </Dialog>
  );
}

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "var(--space-2)",
  fontSize: "var(--text-sm)",
  fontWeight: "var(--weight-medium)",
  color: "var(--text-secondary)",
};

const inputStyle: React.CSSProperties = {
  height: 34,
  padding: "0 var(--space-3)",
  background: "var(--bg-surface)",
  border: "1px solid var(--border-default)",
  borderRadius: "var(--radius-md)",
  color: "var(--text-primary)",
  fontSize: "var(--text-sm)",
  fontWeight: "var(--weight-normal)",
};

function truncate(s: string, n: number): string {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}
