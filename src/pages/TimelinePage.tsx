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
 *   · 分类色标记时间轴节点与类别，不覆盖整条记录
 *   · 生产力分数用「色点 + 数字 + 文字」三重表达，不只靠颜色
 */

import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { useRecording } from "@/lib/useRecording";
import { ActivityCard, ApiError, api } from "@/lib/api";
import {
  CATEGORIES,
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
import { Badge, Button, EmptyState, Input, MetaChip, NumberStepper, Select, Toast, Tooltip } from "@/components/ui";
import { LineIcon } from "@/components/LineIcon";
import { useLatest } from "@/lib/useLatest";
import { isReducedMotionActive, pendingMotion, useExit } from "@/lib/motion";
import { Dialog, DialogBody, DialogFooter, DialogHeader } from "@/components/Dialog";
import { LoadingHandoff } from "@/components/LoadingHandoff";

const EMPTY_CARDS: ActivityCard[] = [];

export function TimelinePage({
  date,
  onDateChange,
  onOpenReports,
  active,
  activityFocus,
  recordingControl,
}: {
  date: string;
  onDateChange: (d: string) => void;
  onOpenReports: () => void;
  active: boolean;
  activityFocus: { day: string; id: number } | null;
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
  const [dateTransition, setDateTransition] = useState<{ date: string; dir: "prev" | "next" | "jump" }>({
    date,
    dir: "jump",
  });
  if (dateTransition.date !== date) {
    setDateTransition({ date, dir: date < dateTransition.date ? "prev" : "next" });
  }
  const [removingIds, setRemovingIds] = useState<Set<number>>(() => new Set());
  const [deletingIds, setDeletingIds] = useState<Set<number>>(() => new Set());
  const deletingIdsRef = useRef<Set<number>>(new Set());
  const [editing, setEditing] = useState<ActivityCard | null>(null);
  const [toast, setToast] = useState<{ card: ActivityCard; date: string; undoToken?: string }[]>([]);
  const [undoBusy, setUndoBusy] = useState(false);
  const [undoFailed, setUndoFailed] = useState(false);
  const [restoredFeedback, setRestoredFeedback] = useState("");
  const toastGeneration = useRef(0);
  const toastTimer = useRef<number | null>(null);
  const [toastClosing, setToastClosing] = useState(false);
  const [toastPaused, setToastPaused] = useState(false);
  const toastPausedRef = useRef(false);
  const UNDO_MS = 10000;
  const toastRemaining = useRef(UNDO_MS);
  const toastStartedAt = useRef<number | null>(null);
  const toastElement = useRef<HTMLDivElement>(null);
  const [editClosing, setEditClosing] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");
  const request = useRef(0);
  const quietRequest = useRef(0);
  const foregroundLoading = useRef(false);
  const mutationVersion = useRef(0);
  const mutating = useRef(0);
  const focusedRequest = useRef<typeof activityFocus>(null);
  const fastPoll = recordingControl.state?.recordingMode === "local" && recordingControl.state.isRecording;

  const clearToastTimer = () => {
    if (toastTimer.current !== null) {
      window.clearTimeout(toastTimer.current);
      toastTimer.current = null;
    }
  };

  const startToastTimer = (ms = UNDO_MS) => {
    clearToastTimer();
    toastRemaining.current = ms;
    toastStartedAt.current = performance.now();
    toastTimer.current = window.setTimeout(() => {
      toastTimer.current = null;
      toastStartedAt.current = null;
      setToastClosing(true);
    }, ms);
  };

  const pauseToastTimer = () => {
    if (!toast.length || toastPausedRef.current || toastClosing || undoBusy || undoFailed) return;
    toastPausedRef.current = true;
    setToastPaused(true);
    if (toastStartedAt.current !== null) {
      toastRemaining.current = Math.max(0, toastRemaining.current - (performance.now() - toastStartedAt.current));
      toastStartedAt.current = null;
    }
    clearToastTimer();
  };

  const resumeToastTimer = () => {
    if (!toastPausedRef.current) return;
    toastPausedRef.current = false;
    setToastPaused(false);
    if (!toastClosing && !undoBusy && !undoFailed && toast.length > 0) {
      startToastTimer(toastRemaining.current);
    }
  };

  useExit(toastElement, toastClosing, () => {
    setToast([]);
    setRestoredFeedback("");
    setToastClosing(false);
    toastPausedRef.current = false;
    setToastPaused(false);
  });

  const closeEdit = () => setEditClosing(true);

  useEffect(() => {
    return () => {
      request.current++;
      if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    };
  }, []);

  const load = async (d: string, quiet = false) => {
    if (d !== currentDate.current) return;
    if (quiet && (mutating.current || foregroundLoading.current)) return;

    if (quiet) {
      const fgVersion = request.current;
      const qid = ++quietRequest.current;
      const mutAtStart = mutationVersion.current;
      try {
        const res = await api.getCards(d);
        if (
          fgVersion !== request.current ||
          qid !== quietRequest.current ||
          mutAtStart !== mutationVersion.current ||
          d !== currentDate.current ||
          mutating.current
        ) return;
        setError(null);
        const next = Array.isArray(res?.cards) ? res.cards : [];
        setCards((previous) => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
        setFilter((current) => current && !next.some((card) => (card.category || "其他") === current) ? null : current);
      } catch {
        /* 静默刷新失败不覆盖当前已展示内容 */
      }
      return;
    }

    const id = ++request.current;
    ++quietRequest.current;
    const mutAtStart = mutationVersion.current;
    foregroundLoading.current = true;
    setLoading(true);
    setError(null);
    let refreshedAfterMutation = false;
    try {
      const res = await api.getCards(d);
      /* 后端少返回一个字段就整页崩溃没有意义。
         日报页已经栽过一次同样的跟头。 */
      if (id !== request.current) return;
      if (mutAtStart !== mutationVersion.current) {
        refreshedAfterMutation = true;
        if (d === currentDate.current) void load(d, false);
        return;
      }
      setError(null);
      const next = Array.isArray(res?.cards) ? res.cards : [];
      setCards(next);
      setFilter((current) => current && !next.some((card) => (card.category || "其他") === current) ? null : current);
    } catch (e) {
      if (id !== request.current) return;
      setError(e instanceof ApiError ? e.message : "加载失败");
      setCards([]);
    } finally {
      if (!refreshedAfterMutation && id === request.current) {
        foregroundLoading.current = false;
        setLoadedDate(d);
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    load(date);
    return () => {
      request.current++;
      quietRequest.current++;
      foregroundLoading.current = false;
    };
  }, [date]);

  useEffect(() => {
    if (!active || loadedDate !== date || date !== todayStr()) return;
    const timer = window.setInterval(() => { if (!document.hidden) void load(date, true); }, fastPoll ? 2000 : 8000);
    return () => window.clearInterval(timer);
  }, [active, loadedDate, date, fastPoll]);

  useEffect(() => {
    if (!activityFocus) return;
    setFilter(null);
    setQuery("");
  }, [activityFocus]);

  // 分类计数与时长占比（驱动顶部 4px 类别比例微条）
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of cards) m.set(c.category || "其他", (m.get(c.category || "其他") ?? 0) + 1);
    return m;
  }, [cards]);

  const categoryMinutes = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of cards) {
      const cat = c.category || "其他";
      m.set(cat, (m.get(cat) ?? 0) + Math.max(1, c.durationMinutes));
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
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

  useEffect(() => {
    if (!active || !activityFocus || activityFocus.day !== date || focusedRequest.current === activityFocus) return;
    const row = document.getElementById(`activity-${activityFocus.id}`);
    if (!row) return;
    focusedRequest.current = activityFocus;
    row.scrollIntoView({ block: "center" });
    row.focus({ preventScroll: true });
  }, [active, activityFocus, date, visible]);

  const totals = useMemo(() => {
    let mins = 0;
    let deepMins = 0;
    let scoreWeighted = 0;
    let scoreMins = 0;
    for (const c of cards) {
      mins += c.durationMinutes;
      if (c.durationMinutes >= 60) deepMins += c.durationMinutes;
      if (c.productivityScore > 0) {
        const w = Math.max(1, c.durationMinutes);
        scoreWeighted += c.productivityScore * w;
        scoreMins += w;
      }
    }
    return {
      count: cards.length,
      minutes: mins,
      deepMinutes: deepMins,
      avgScore: scoreMins > 0 ? Math.round(scoreWeighted / scoreMins) : 0,
    };
  }, [cards]);

  const clearRemoving = (id: number) => {
    deletingIdsRef.current.delete(id);
    setDeletingIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    setRemovingIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const handleDelete = async (card: ActivityCard) => {
    if (deletingIdsRef.current.has(card.id)) return;
    deletingIdsRef.current.add(card.id);
    setDeletingIds((prev) => {
      const next = new Set(prev);
      next.add(card.id);
      return next;
    });
    setOperationError(null);
    mutating.current++;
    try {
      let deleted: Awaited<ReturnType<typeof api.deleteCard>>;
      try {
        deleted = await api.deleteCard(card.id);
      } catch (error) {
        clearRemoving(card.id);
        if (date === currentDate.current) {
          setOperationError(error instanceof ApiError ? error.message : "未能删除活动，请重试");
        }
        return;
      }

      mutationVersion.current++;
      const remove = () => {
        clearRemoving(card.id);
        if (date === currentDate.current) setCards((cs) => cs.filter((c) => c.id !== card.id));
      };
      try {
        const row = date === currentDate.current ? document.getElementById(`activity-${card.id}`) : null;
        const animate = row && !isReducedMotionActive() && row.getClientRects().length > 0;
        if (animate) {
          flushSync(() => setRemovingIds((ids) => new Set(ids).add(card.id)));
          const motion = pendingMotion(row);
          if (motion) await motion;
        }
        if (row?.contains(document.activeElement)) {
          const next = row.nextElementSibling ?? row.previousElementSibling ?? document.getElementById("timeline-heading");
          if (next instanceof HTMLElement) next.focus({ preventScroll: true });
        }
        if (animate && row.isConnected && !isReducedMotionActive()) moveRowsAfterRemoval(row, remove);
        else remove();
      } catch {
        // A visual transition must not undo a committed deletion or lose its token.
        remove();
      }
      toastGeneration.current++;
      setToast((items) => [...items, { card, date, undoToken: deleted?.undoToken }]);
      setRestoredFeedback("");
      setToastClosing(false);
      setUndoFailed(false);
      toastPausedRef.current = false;
      setToastPaused(false);
      startToastTimer(UNDO_MS);
    } finally {
      mutating.current--;
      if (date === currentDate.current) void load(date, true);
    }
  };

  const handleUndo = async () => {
    if (!toast.length || undoBusy) return;
    const generation = toastGeneration.current;
    clearToastTimer();
    toastStartedAt.current = null;
    toastPausedRef.current = false;
    setToastPaused(false);
    setUndoBusy(true);
    setUndoFailed(false);
    setToastClosing(false);
    mutating.current++;
    const failed = new Set<number>();
    try {
      for (const { card, date: deletedOn, undoToken } of toast) {
        try {
          await api.restoreCard(card, undoToken);
          mutationVersion.current++;
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
      if (failed.size) clearToastTimer();
      else if (toastGeneration.current === generation) {
        setRestoredFeedback(`已恢复 ${toast.length} 条活动`);
        startToastTimer(1200);
      }
    } finally {
      mutating.current--;
      setUndoBusy(false);
      void load(currentDate.current, true);
    }
  };

  const handleSave = async (card: ActivityCard) => {
    setEditError("");
    setEditSaving(true);
    mutating.current++;
    try {
      await api.updateCard(card.id, card);
      mutationVersion.current++;
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

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <header className="df-timeline-head df-timeline-container">
        <h2 id="timeline-heading" className="df-page-title" tabIndex={-1}>时间轴</h2>
        <div className="df-timeline-controls">
          <div className="df-datenav">
            <IconButton
              label="前一天"
              onClick={() => onDateChange(shiftDate(date, -1))}
            >
              <LineIcon name="chevron-left" size={16} />
            </IconButton>
            <div className="df-datelabel">
              <div
                key={date}
                className="df-date-shift"
                data-dir={dateTransition.dir}
              >
                <time dateTime={date} title={fullDate(date)}>
                  {isToday(date) ? "今天" : prettyDate(date)}
                  {isToday(date) && <span className="df-timeline-full-date">{date}</span>}
                </time>
              </div>
            </div>
            <IconButton
              label="后一天"
              onClick={() => onDateChange(shiftDate(date, 1))}
              disabled={date >= todayStr()}
            >
              <LineIcon name="chevron-right" size={16} />
            </IconButton>
          </div>

          {!isToday(date) && (
            <span className="df-fade-up">
              <Button size="sm" variant="ghost" onClick={() => onDateChange(todayStr())}>
                回到今天
              </Button>
            </span>
          )}

          <Button size="sm" variant="ghost" onClick={onOpenReports}>
            <LineIcon name="file" size={14} />
            <span>日报</span>
          </Button>
          <SearchBox value={query} onChange={setQuery} />
        </div>
      </header>

      {operationError && (
        <div className="df-inline-notice df-feedback" role="alert">
          <span>{operationError}</span>
          <Button size="sm" variant="ghost" onClick={() => setOperationError(null)}>关闭</Button>
        </div>
      )}

      <div className="df-timeline-scroll">
        <div className="df-timeline-container">
          <LoadingHandoff
            loading={loading || loadedDate !== date}
            retainOnReload
            skeleton={
              <div
                style={{
                  padding: "var(--space-5) 0",
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
                icon={<LineIcon name="alert" size={28} />}
                title="加载失败"
                description={error}
                action={<Button onClick={() => load(date)}>重试</Button>}
              />
            ) : (
              <>
                {cards.length > 0 && (
                  <section className="df-day-summary" aria-label="当日概览">
                    <dl className="df-day-metrics">
                      <div className="df-day-metric df-day-metric-primary">
                        <dt>记录时长</dt>
                        <dd>{formatMinutes(totals.minutes)}</dd>
                      </div>
                      <div className="df-day-metric">
                        <dt>活动数</dt>
                        <dd>{totals.count}</dd>
                      </div>
                      {totals.deepMinutes > 0 && (
                        <div className="df-day-metric">
                          <dt>深度工作</dt>
                          <dd>{formatMinutes(totals.deepMinutes)}</dd>
                        </div>
                      )}
                      {totals.avgScore > 0 && (
                        <div className="df-day-metric">
                          <dt>专注评分</dt>
                          <dd style={{ color: `var(${scoreVar(totals.avgScore)})` }}>
                            {totals.avgScore}% <small>{scoreLabel(totals.avgScore)}</small>
                          </dd>
                        </div>
                      )}
                    </dl>

                    {categoryMinutes.length > 0 && (
                      <div className="df-composition-bar" aria-hidden="true">
                        {categoryMinutes.map(([cat, mins]) => (
                          <span
                            key={cat}
                            className="df-composition-seg"
                            style={{
                              flex: mins,
                              background: `var(${categoryVar(cat)})`,
                              opacity: filter && filter !== cat ? 0.22 : 1,
                            }}
                          />
                        ))}
                      </div>
                    )}
                  </section>
                )}

                {cards.length > 0 && (
                  <div className="df-activity-toolbar">
                    <h3>活动记录</h3>
                    <div className="df-pill-row" role="group" aria-label="按活动类别筛选">
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
                  </div>
                )}

                {visible.length === 0 ? (
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
                        highlighted={activityFocus?.day === date && activityFocus.id === card.id}
                        removing={removingIds.has(card.id)}
                        deleting={deletingIds.has(card.id)}
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
              </>
            )}
          </LoadingHandoff>
        </div>
      </div>

      {editing && (
        <EditDialog
          key={editing.id}
          card={editing}
          open={!editClosing}
          onClose={() => { if (!editSaving) closeEdit(); }}
          saving={editSaving}
          error={editError}
          onExited={() => setEditing(null)}
          onSave={handleSave}
        />
      )}

      {(toast.length > 0 || restoredFeedback) && (
        <Toast
          ref={toastElement}
          position="bottom"
          closing={toastClosing}
          paused={toastPaused}
          countdownKey={!undoBusy && !undoFailed ? toast[toast.length - 1]?.card.id : undefined}
          reducedHint={!undoFailed && !restoredFeedback ? "（10 秒内可撤销）" : undefined}
          onMouseEnter={pauseToastTimer}
          onMouseLeave={(e) => {
            if (!e.currentTarget.contains(document.activeElement)) resumeToastTimer();
          }}
          onFocus={pauseToastTimer}
          onBlur={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null) && !e.currentTarget.matches(":hover")) {
              resumeToastTimer();
            }
          }}
          action={restoredFeedback ? undefined :
            <>
              <Button size="sm" variant="ghost" onClick={handleUndo} loading={undoBusy} disabled={toastClosing}>
                {undoFailed ? "重试" : "撤销"}
              </Button>
              {undoFailed && (
                <Button size="sm" variant="ghost" onClick={() => setToastClosing(true)} disabled={toastClosing}>
                  关闭
                </Button>
              )}
            </>
          }
        >
          {restoredFeedback || (undoFailed ? `未能恢复 ${toast.length} 条活动` : toast.length === 1
            ? `已删除「${truncate(toast[0].card.title, 18)}」`
            : `已删除 ${toast.length} 条活动`)}
        </Toast>
      )}
    </div>
  );
}

// ── 单条活动 ──────────────────────────────────────────────

// Measure visible siblings once on each side of the DOM update, then move only
// those rows with a transform. Interrupted moves resume from their current position.
function moveRowsAfterRemoval(row: HTMLElement, remove: () => void) {
  const bounds = row.closest(".df-timeline-scroll")?.getBoundingClientRect();
  const positions: { item: HTMLElement; top: number }[] = [];
  if (bounds && row.getBoundingClientRect().bottom >= bounds.top) {
    for (let item = row.nextElementSibling; item instanceof HTMLElement; item = item.nextElementSibling) {
      const rect = item.getBoundingClientRect();
      if (rect.top > bounds.bottom) break;
      positions.push({ item, top: rect.top });
    }
  }
  if (!positions.length) return remove();

  const style = getComputedStyle(row);
  const duration = Number.parseFloat(style.getPropertyValue("--dur-space"));
  const easing = style.getPropertyValue("--ease-out").trim();
  flushSync(remove);
  for (const { item } of positions) {
    item.getAnimations().find((animation) => animation.id === "dayflow-row-shift")?.cancel();
  }
  const offsets = positions.filter(({ item }) => item.isConnected)
    .map(({ item, top }) => ({ item, delta: top - item.getBoundingClientRect().top }));
  for (const { item, delta } of offsets) {
    if (Math.abs(delta) < 1) continue;
    const animation = item.animate({ translate: [`0 ${delta}px`, "0 0"] }, { duration, easing });
    animation.id = "dayflow-row-shift";
  }
}

function ActivityRow({
  card,
  highlighted,
  removing,
  deleting,
  onEdit,
  onDelete,
}: {
  card: ActivityCard;
  highlighted: boolean;
  removing?: boolean;
  deleting?: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const score = card.productivityScore;
  const apps = card.appSites.slice(0, 3);

  return (
    <div
      className="df-row"
      id={`activity-${card.id}`}
      tabIndex={-1}
      data-evidence={highlighted || undefined}
      data-removing={removing || undefined}
    >
      {/* 时间列：固定宽度，让所有条目的时间戳垂直对齐 */}
      <div className="df-row-time">
        <div style={{ color: "var(--text-secondary)" }}>
          {formatClock(card.displayStartTime ?? card.startTime)}
        </div>
        <div style={{ marginTop: 1 }}>{formatMinutes(card.durationMinutes)}</div>
      </div>

      {/* 分类色节点落在贯穿列表的时间轨上。 */}
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
              <MetaChip key={a.name}>{a.name}</MetaChip>
            ))}
            {card.appSites.length > 3 && (
              <MetaChip>+{card.appSites.length - 3}</MetaChip>
            )}
          </div>
        )}
      </div>

      {/* 操作：悬停/聚焦才出现，但始终可 Tab 到。
          触屏没有 hover —— df-hover-only 在 (hover: none) 下强制显形，
          否则编辑和删除在手机上等于不存在。

          窄屏下图标替代文字：两个 28px 的文字按钮会占掉近一半宽度。 */}
      <div className="df-hover-only df-row-actions">
        <Button size="sm" variant="ghost" onClick={onEdit} disabled={deleting || removing} aria-label="编辑">
          <span className="df-actions-label">编辑</span>
          <span className="df-actions-icon" aria-hidden><LineIcon name="edit" size={14} /></span>
        </Button>
        <Button size="sm" variant="ghost" onClick={onDelete} aria-label="删除" loading={deleting}>
          <span className="df-actions-label">删除</span>
          <span className="df-actions-icon" aria-hidden><LineIcon name="trash" size={14} /></span>
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
    <Tooltip content={label} placement="bottom" disabled={disabled}>
      <button
        type="button"
        aria-label={label}
        disabled={disabled}
        onClick={onClick}
        /* 28×28 的按钮很难点中。伪元素纵向扩到 42px；
           横向不扩 —— 前一天/后一天中心距只有 32px，
           各自横扩到 40px 会互相盖住对方的点击区。
           横向 28px 本身已过 24px 的底线。 */
        className="df-icon-btn df-hit-v"
      >
        {children}
      </button>
    </Tooltip>
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
      className="df-pill"
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
    </button>
  );
}

function SearchBox({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="df-search-wrap">
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="搜索活动"
        aria-label="搜索活动标题、摘要或类别"
        className="df-search"
        data-filled={value ? "true" : undefined}
      />
      <span aria-hidden className="df-search-icon">
        <LineIcon name="search" size={14} />
      </span>
      {value && (
        <button
          type="button"
          className="df-search-clear"
          aria-label="清除搜索"
          onClick={() => onChange("")}
        >
          <LineIcon name="x" size={12} />
        </button>
      )}
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
  const local = state?.recordingMode !== "visual";
  const action = local ? "计时" : "录制";
  if (isFiltered) {
    return <EmptyState icon={<LineIcon name="search" size={28} />} title="没有匹配的活动"
      description="换个关键词，或查看全部记录。"
      action={<Button onClick={onClearFilter}>清除筛选</Button>} />;
  }
  if (!isToday) {
    return <EmptyState icon={<LineIcon name="inbox" size={28} />} title="这一天没有活动记录"
      description="可以在上方选另一天，或回到今天。" />;
  }
  if (state?.isRecording) {
    const paused = state.isPaused || state.isIdlePaused;
    return <EmptyState icon={<LineIcon name="clock" size={28} />} title={paused ? `${action}已暂停` : state.isPrivacyPaused ? "隐私保护已暂停记录" : local ? "正在记录应用用时" : "正在整理今天的活动"}
      description={paused ? "继续后，新的活动会陆续出现。"
        : state.isPrivacyPaused ? "关闭敏感窗口或恢复显示器布局后，记录会自动继续。" : "活动会自动显示在这里。"}
      action={paused && <Button variant="primary" loading={pending === "resume"}
        onClick={() => run("resume")}>继续{action}</Button>} />;
  }
  return <EmptyState icon={<LineIcon name="clock" size={28} />} title="今天还没有活动记录"
    description={state?.needsSetup ? "连接模型后即可启用截图分析。"
      : local ? "只在这台电脑记录前台应用和用时，无需联网或填写模型密钥。" : "录制开始后，活动会自动整理在这里。"}
    action={<Button variant="primary" loading={pending === "start"} onClick={() => run("start")}>
      {state?.needsSetup ? "连接分析模型" : `开始${action}`}
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
      <DialogHeader id="editDialogTitle" title="编辑活动" description="修改后的标题与类别会立即同步到时间轴与统计。" />
      <DialogBody>
        <fieldset disabled={saving} className="df-edit-fields">
          <label style={labelStyle}>
            标题
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={{ width: "100%" }}
            />
          </label>

          <label style={labelStyle}>
            类别
            <Select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              style={{ width: "100%" }}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </label>

          <div style={labelStyle}>
            <span>生产力评分</span>
            <NumberStepper
              ariaLabel="生产力评分"
              min={0}
              max={100}
              step={5}
              unit="分"
              presets={[60, 80, 95]}
              value={score}
              disabled={saving}
              onChange={(v) => {
                const n = Number(v);
                setScore(Number.isFinite(n) ? Math.max(0, Math.min(100, Math.round(n))) : 0);
              }}
            />
          </div>

          <label style={labelStyle}>
            摘要
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              rows={3}
              className="df-field"
              style={{ height: "auto", padding: "8px var(--space-3)", resize: "vertical", width: "100%" }}
            />
          </label>
        </fieldset>
        {error && <p role="alert" className="df-feedback" style={{ color: "var(--danger)" }}>{error}</p>}
      </DialogBody>
      <DialogFooter>
        <Button onClick={onClose} disabled={saving}>取消</Button>
        <Button
          variant="primary" loading={saving} disabled={!title.trim()}
          onClick={() =>
            onSave({ ...card, title, summary, category, productivityScore: score })
          }
        >
          保存
        </Button>
      </DialogFooter>
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

function truncate(s: string, n: number): string {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}
