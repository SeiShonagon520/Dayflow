/*
 * 应用外壳
 *
 * 侧边栏在三个阶段之间切换，依据是内容还剩多少可用宽度，
 * 不是设备叫什么名字：
 *
 *   ≥1000px  完整侧栏 200px，图标 + 文字
 *   ≥620px   图标栏 56px，只留图标，文字转 tooltip
 *   <620px   底部标签栏，导航移到拇指区，主操作留在底部
 *
 * 旧版固定 200px 不动。实测 320px 下内容区只剩 118px，
 * 活动标题整行不可见 —— 不是挤，是没了。
 *
 * 窗口边框用 border 而不是 box-shadow：frameless 窗口没有系统边框，
 * 1px 描边是唯一能让窗口边界可见的办法。
 */

import { ReactNode, useEffect, useRef, useState } from "react";
import { ApiError, RecordingState, api } from "@/lib/api";
import { Button } from "@/components/ui";
import { FocusRing } from "@/components/FocusRing";
import { LineIcon, LineIconName } from "@/components/LineIcon";
import { useIsNarrow, useIsPhone } from "@/lib/useMediaQuery";

export type PageKey = "timeline" | "reports" | "stats" | "settings";

const NAV: { key: PageKey; label: string; icon: LineIconName }[] = [
  { key: "timeline", label: "时间轴", icon: "clock" },
  { key: "reports", label: "日报", icon: "file" },
  { key: "stats", label: "统计", icon: "chart" },
  { key: "settings", label: "设置", icon: "settings" },
];

function NavItem({
  item,
  active,
  collapsed,
  onClick,
}: {
  item: { key: PageKey; label: string; icon: LineIconName };
  active: boolean;
  collapsed: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      /* 收起成图标栏时，文字不可见但必须仍可读 —— 读屏和
         悬停提示都靠这个。title 同时兜底原生 tooltip。 */
      aria-label={collapsed ? item.label : undefined}
      title={collapsed ? item.label : undefined}
      className={`df-nav-item${active ? " is-active" : ""}`}
      data-collapsed={collapsed ? "true" : "false"}
    >
      <span aria-hidden style={{ width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <LineIcon name={item.icon} />
      </span>
      {!collapsed && <span>{item.label}</span>}
      <FocusRing />
    </button>
  );
}

function RecordingStatus({
  recording,
  paused,
  compact,
}: {
  recording: boolean;
  paused: boolean;
  compact: boolean;
}) {
  return (
    <div
      className="df-rec-status"
      data-compact={compact ? "true" : "false"}
      title={compact ? (recording ? (paused ? "录制已暂停" : "录制中") : "未录制")
                      : undefined}
    >
      {recording && (
        <span
          aria-hidden
          className="df-rec-dot"
          style={{
            background: "var(--recording)",
            animation: "df-pulse 1.6s var(--ease-in-out) infinite",
          }}
        />
      )}
      {/* 收起时只留色点，但状态不能只靠颜色表达：
          读屏读到的是 aria-label，视觉用户看到的是色点 + 悬停提示。 */}
      {collapsedLabel(compact, recording, paused)}
    </div>
  );
}

function collapsedLabel(compact: boolean, recording: boolean, paused: boolean) {
  if (!compact) return recording ? (paused ? "已暂停" : "录制中") : "未录制";
  return (
    <span className="u-sr-only">
      {recording ? (paused ? "录制已暂停" : "录制中") : "未录制"}
    </span>
  );
}

export function Shell({
  page,
  onPage,
  onError,
  children,
}: {
  page: PageKey;
  onPage: (p: PageKey) => void;
  onError?: (msg: string | null) => void;
  children: ReactNode;
}) {
  const [rec, setRec] = useState<RecordingState | null>(null);
  /* 主题：后端是唯一真相，localStorage 只是启动缓存。

     之前两边各存各的 —— 这里写 localStorage，设置页把 theme 读出来
     又原样存回后端，谁也不通知谁。结果 Qt 那边改了主题这边不跟，
     这边改了后端不知道，两套界面能显示成不同主题。

     先用 localStorage 起（避免首帧闪一下错误的主题），
     随后以后端为准校正。 */
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("dayflow-theme");
    return saved === "dark" ? "dark" : "light";
  });
  /* 用户在本轮里手动切过就不要被后端覆盖，
     否则刚点的按钮会被一个迟到的响应改回去。 */
  const themeTouched = useRef(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("dayflow-theme", theme);
  }, [theme]);

  useEffect(() => {
    if (themeTouched.current) return;
    api
      .getSettings()
      .then((s) => {
        const t = s.theme === "dark" ? "dark" : s.theme === "light" ? "light" : null;
        if (t && !themeTouched.current) setTheme(t);
      })
      .catch(() => {
        /* 后端没起来就用 localStorage 里的值，不要跳到亮色 */
      });
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    themeTouched.current = true;
    setTheme(next);
    /* 立刻写回后端。失败要说出来 —— 静默失败正是「两个真相源」
       最开始出现的原因。 */
    api
      .saveSettings({ theme: next })
      .then(() => onError?.(null))
      .catch((e) =>
        onError?.(e instanceof ApiError ? e.message : "主题没能保存，重启后会还原"));
  };

  const poll = async () => {
    try {
      setRec(await api.getRecordingState());
    } catch {
      /* 后端还没起来，忽略 */
    }
  };

  useEffect(() => {
    poll();
    const t = window.setInterval(poll, 3000);
    return () => window.clearInterval(t);
  }, []);

  const recording = rec?.isRecording ?? false;
  const paused = rec?.isPaused || rec?.isIdlePaused || false;

  /* 请求在飞的时候把按钮锁住。
     实测连点两次「开始录制」会发出两个 POST /api/recording/start ——
     recording 要等请求返回才翻转，中间那几百毫秒按钮看着还能点。

     锁必须是 ref，不能用 state 判：两次点击可能落在同一次 render 的
     闭包里，都读到 pending === false，然后各自放行 —— 第一版就是这么
     写的，实测 POST 仍是 2 次。ref 的读写是同步的，不受渲染批次影响。
     state 只用来给按钮上禁用态和转圈（视觉反馈）。 */
  const busyRef = useRef(false);
  const [pending, setPending] = useState(false);

  const toggleRecording = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setPending(true);
    try {
      if (recording) {
        await api.stopRecording();
      } else {
        await api.startRecording();
      }
      onError?.(null);
      await poll();
    } catch (e) {
      // 启动失败最常见的是没配 API Key —— 把它说出来，
      // 静默失败会让人以为按钮坏了
      onError?.(e instanceof Error ? e.message : "录制操作失败");
    } finally {
      busyRef.current = false;
      setPending(false);
    }
  };

  const phone = useIsPhone();
  const rail = useIsNarrow();
  /* 手机上不再有侧边栏，导航变成底部标签栏 */
  const collapsed = rail && !phone;

  /* 手机上主操作移到内容底部的拇指区。
     录制是最频繁的动作，不能要求用户伸到屏幕左上角。
     图标栏（56px）放不下「停止录制」四个字，收成图标 + tooltip。 */
  const mainAction = (
    <Button
      variant={recording ? "secondary" : "primary"}
      fullWidth={!collapsed}
      /* 侧栏里是竖排排列，40px 的命中高度不会显得重 */
      size={collapsed ? "md" : phone ? "lg" : "md"}
      onClick={toggleRecording}
      /* 请求在飞时禁用 + 转圈。标签保持不变 ——
         加载中的按钮改名字会让人以为点出了别的状态。 */
      loading={pending}
      title={collapsed
        ? (recording ? "停止录制" : "开始录制")
        : undefined}
      aria-label={recording ? "停止录制" : "开始录制"}
    >
      {!collapsed && (recording ? "停止录制" : "开始录制")}
      <span className="df-rail-glyph" aria-hidden>
        {recording ? "■" : "●"}
      </span>
    </Button>
  );

  const brand = (
    <div className="df-brand">
      <span aria-hidden className="df-brand-mark">
        ◷
      </span>
      {!collapsed && <span className="df-brand-name">Dayflow</span>}
    </div>
  );

  return (
    <div
      className="df-shell"
      data-layout={phone ? "bottom" : collapsed ? "rail" : "full"}
    >
      {/* ── 侧边栏（宽屏 / 平板竖屏） ───────────────────── */}
      {!phone && (
        <nav className="df-sidebar" aria-label="主导航">
          {brand}

          {NAV.map((item) => (
            <NavItem
              key={item.key}
              item={item}
              active={page === item.key}
              collapsed={collapsed}
              onClick={() => onPage(item.key)}
            />
          ))}

          <div style={{ flex: 1 }} />

          <RecordingStatus recording={recording} paused={paused} compact={collapsed} />

          {mainAction}

          <Button
            variant="ghost"
            fullWidth={!collapsed}
            size="sm"
            onClick={toggleTheme}
            title={collapsed
              ? (theme === "dark" ? "切换到亮色" : "切换到暗色")
              : "切换主题"}
            aria-label={theme === "dark" ? "切换到亮色" : "切换到暗色"}
          >
            {!collapsed && (theme === "dark" ? "☀ 亮色" : "☾ 暗色")}
            <span className="df-rail-glyph" aria-hidden>
              {theme === "dark" ? "☀" : "☾"}
            </span>
          </Button>
        </nav>
      )}

      {/* ── 内容区 ─────────────────────────────────────── */}
      <main className="df-main">
        {children}

        {/* 录制状态是后台发生的事，用户看不到屏幕变化。
            没有 live region 的话，录制的启停对读屏用户完全隐形。 */}
        <span
          role="status"
          aria-live="polite"
          className="u-sr-only"
        >
          {recording
            ? (paused ? "录制已暂停" : "正在录制")
            : "未开始录制"}
        </span>

        {/* 手机端：主操作在底部拇指区，导航在它下面 */}
        {phone && (
          <div className="df-phone-dock">
            {mainAction}
            <nav className="df-bottom-nav" aria-label="主导航">
              {NAV.map((item) => (
                <NavItem
                  key={item.key}
                  item={item}
                  active={page === item.key}
                  collapsed={false}
                  onClick={() => onPage(item.key)}
                />
              ))}
            </nav>
          </div>
        )}
      </main>
    </div>
  );
}
