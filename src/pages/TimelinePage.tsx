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

import { useEffect, useMemo, useRef, useState } from "react";
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
import { Dialog } from "@/components/Dialog";
import { LoadingHandoff } from "@/components/LoadingHandoff";
import { FocusRing } from "@/components/FocusRing";

export function TimelinePage({
  date,
  onDateChange,
  onOpenReports,
  onStartRecording,
}: {
  date: string;
  onDateChange: (d: string) => void;
  onOpenReports: () => void;
  onStartRecording: () => void;
}) {
  const [cards, setCards] = useState<ActivityCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<ActivityCard | null>(null);
  const [toast, setToast] = useState<{ msg: string; card: ActivityCard } | null>(
    null
  );
  const toastTimer = useRef<number | null>(null);
  /* 退场中：toast 已清空但 DOM 还留着播动画 */
  const [toastClosing, setToastClosing] = useState(false);
  const exitTimer = useRef<number | null>(null);

  /** 撤销窗口。必须和 CSS 里的 --undo-window 一致，
      否则倒计时条走完、条子还在（或反过来）。 */
  const UNDO_MS = 6000;

  /** 退场时长，和 CSS 里的 --dur-exit 一致。改一个要改两个。 */
  const EXIT_MS = 150;

  /** 先播退场，再卸载。真正的消失推迟 150ms。 */
  const dismissToast = () => {
    setToastClosing(true);
    if (exitTimer.current !== null) window.clearTimeout(exitTimer.current);
    exitTimer.current = window.setTimeout(
      () => setToastClosing(false), EXIT_MS);
  };

  /* 退场中：editing 还在，但对话框在关闭。 */
  const [editClosing, setEditClosing] = useState(false);
  const editTimer = useRef<number | null>(null);

  /** 请求关闭：先播退场，EXIT_MS 后才真正卸载。 */
  const closeEdit = () => {
    setEditClosing(true);
    if (editTimer.current !== null) window.clearTimeout(editTimer.current);
    editTimer.current = window.setTimeout(() => {
      setEditing(null);
      setEditClosing(false);
    }, EXIT_MS);
  };

  useEffect(() => () => {
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    if (exitTimer.current !== null) window.clearTimeout(exitTimer.current);
    if (editTimer.current !== null) window.clearTimeout(editTimer.current);
  }, []);

  const load = async (d: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getCards(d);
      /* 后端少返回一个字段就整页崩溃没有意义。
         日报页已经栽过一次同样的跟头。 */
      setCards(Array.isArray(res?.cards) ? res.cards : []);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "加载失败");
      setCards([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(date);
  }, [date]);

  // 分类计数
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of cards) m.set(c.category || "其他", (m.get(c.category || "其他") ?? 0) + 1);
    return m;
  }, [cards]);

  const visible = useMemo(() => {
    let list = cards;
    if (filter) list = list.filter((c) => (c.category || "其他") === filter);
    if (query.trim()) {
      const q = query.trim().toLowerCase();
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
  }, [cards, filter, query]);

  const totals = useMemo(() => {
    const mins = cards.reduce((s, c) => s + c.durationMinutes, 0);
    return { count: cards.length, minutes: mins };
  }, [cards]);

  const showToast = (msg: string, card: ActivityCard) => {
    setToast({ msg, card });
    setToastClosing(false);
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    if (exitTimer.current !== null) window.clearTimeout(exitTimer.current);
    // 6 秒后走退场，不直接消失
    toastTimer.current = window.setTimeout(() => {
      setToast(null);
      dismissToast();
    }, UNDO_MS);
  };

  const handleDelete = async (card: ActivityCard) => {
    const snapshot = cards;
    setCards((cs) => cs.filter((c) => c.id !== card.id));
    try {
      await api.deleteCard(card.id);
      showToast(`已删除「${truncate(card.title, 18)}」`, card);
    } catch (e) {
      setCards(snapshot); // 删失败就恢复，不能让界面和数据不一致
      setError(e instanceof ApiError ? e.message : "删除失败");
    }
  };

  const handleUndo = async () => {
    if (!toast) return;
    const card = toast.card;
    /* 撤销后条子立刻没用处了 —— 直接卸载，不播退场。
       慢一秒消失只会让人以为撤销失败了。 */
    setToast(null);
    setToastClosing(false);
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    if (exitTimer.current !== null) window.clearTimeout(exitTimer.current);
    try {
      await api.restoreCard(card);
      setCards((cs) => [...cs, card]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "恢复失败，刷新后该记录会消失");
    }
  };

  const handleSave = async (card: ActivityCard) => {
    setCards((cs) => cs.map((c) => (c.id === card.id ? { ...c, ...card } : c)));
    closeEdit();
    try {
      await api.updateCard(card.id, card);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "保存失败");
      load(date);
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
              <div style={{
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

          {!phone && (
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

      {/* ── 列表 ───────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: "auto", position: "relative" }}>
        <LoadingHandoff
          loading={loading}
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
            hasAny={cards.length > 0}
            isFiltered={!!filter || !!query}
            onStart={onStartRecording}
            onClearFilter={() => {
              setFilter(null);
              setQuery("");
            }}
          />
        ) : (
          <div className="df-row-list">
            {visible.map((card, i) => (
              <ActivityRow
                key={card.id}
                card={card}
                index={i}
                onEdit={() => {
                  setEditClosing(false);
                  setEditing(card);
                }}
                onDelete={() => handleDelete(card)}
              />
            ))}
          </div>
        )}
        </LoadingHandoff>
      </div>

      {/* 对话框：editing 保留到退场结束。
          之前 {editing && <EditDialog/>} 在 closeEdit 里立刻把
          editing 置 null，Dialog 整个被卸载，退场动画没机会播 ——
          实测采样只有 gone/gone/gone。改成用 open 状态控制，
          组件本身活到退场结束。 */}
      {editing && (
        <EditDialog
          card={editing}
          open={!editClosing}
          onClose={closeEdit}
          onSave={handleSave}
        />
      )}

      {/* 撤销条：6 秒后自动消失。
          之前是 setToast(null) 直接卸载，条子凭空蒸发 ——
          用户刚看到「已删除」，撤销机会就闪了一下没了。
          退场动画 + 延后卸载，让它体面地走。

          底部那条线是倒计时。用户看不到 6 秒这个数，
          不知道还剩多久，只能盯着条子消失 ——
          有条线才知道该不该现在按撤销。 */}
      {(toast || toastClosing) && (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "fixed",
            bottom: "var(--space-6)",
            left: "50%",
            transform: "translateX(-50%)",
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
          className={toastClosing ? "df-fade-out" : "df-pop-in"}
        >
          <span style={{ fontSize: "var(--text-sm)" }}>
            {toast ? toast.msg : ""}
          </span>
          {!toastClosing && (
            <Button size="sm" variant="ghost" onClick={handleUndo}>
              撤销
            </Button>
          )}
          {!toastClosing && (
            /* 纯装饰：role=status 已经播报了「已删除」，
               进度条每帧都在变，播报它只会刷屏。
               所以 aria-hidden，不参与可访问性树。 */
            <span
              aria-hidden
              className="df-undo-timer"
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                bottom: 0,
                height: 2,
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}

// ── 单条活动 ──────────────────────────────────────────────

function ActivityRow({
  card,
  index,
  onEdit,
  onDelete,
}: {
  card: ActivityCard;
  index: number;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const score = card.productivityScore;
  const apps = card.appSites.slice(0, 3);

  return (
    <div
      className="df-row"
      style={{
        animation: "df-fade-up var(--dur-space) var(--ease-out) backwards",
        animationDelay: `${Math.min(index, 8) * 18}ms`,
      }}
      onMouseEnter={() => setMenuOpen(true)}
      onMouseLeave={() => setMenuOpen(false)}
    >
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
      <div
        className="df-hover-only df-row-actions"
        data-revealed={menuOpen ? "true" : "false"}
        // 键盘用户即使没悬停也要能看到
        onFocus={() => setMenuOpen(true)}
      >
        <Button size="sm" variant="ghost" onClick={onEdit} title="编辑">
          <span className="df-actions-label">编辑</span>
          <span className="df-actions-icon" aria-hidden>✎</span>
        </Button>
        <Button size="sm" variant="ghost" onClick={onDelete} title="删除">
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
  hasAny,
  isFiltered,
  onStart,
  onClearFilter,
}: {
  hasAny: boolean;
  isFiltered: boolean;
  onStart: () => void;
  onClearFilter: () => void;
}) {
  if (isFiltered) {
    return (
      <EmptyState
        icon="⌕"
        title="没有匹配的活动"
        description="换个关键词，或清除筛选条件查看全部记录。"
        action={<Button onClick={onClearFilter}>清除筛选</Button>}
      />
    );
  }
  if (hasAny) {
    return (
      <EmptyState
        icon="📭"
        title="这一天没有活动记录"
        description="当天录了屏，但没有分析出活动。\n可能是录制时长太短，或分析还没完成。"
      />
    );
  }
  return (
    <EmptyState
      icon="⏱"
      title="今天还没有活动记录"
      description="开始录制后，Dayflow 会每隔几分钟分析一次屏幕活动，自动整理成时间轴。"
      action={<Button variant="primary" onClick={onStart}>开始录制</Button>}
    />
  );
}

// ── 编辑对话框 ────────────────────────────────────────────

function EditDialog({
  card,
  open,
  onClose,
  onSave,
}: {
  card: ActivityCard;
  open: boolean;
  onClose: () => void;
  onSave: (c: ActivityCard) => void;
}) {
  const [title, setTitle] = useState(card.title);
  const [summary, setSummary] = useState(card.summary);
  const [category, setCategory] = useState(card.category);
  const [score, setScore] = useState(Math.round(card.productivityScore));

  /* Esc 和焦点循环都由 Dialog 统一处理，这里不要重复监听 ——
     两个 handler 都会跑，onClose 会被调两次。 */

  return (
    <Dialog open={open} onClose={onClose} labelledBy="editDialogTitle">
        <h3 id="editDialogTitle">编辑活动</h3>

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

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: "var(--space-2)",
          }}
        >
          <Button onClick={onClose}>取消</Button>
          <Button
            variant="primary"
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
