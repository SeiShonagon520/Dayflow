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
import { ApiError, api } from "@/lib/api";
import { Button } from "@/components/ui";
import { FocusRing } from "@/components/FocusRing";
import { LineIcon, LineIconName } from "@/components/LineIcon";
import { useIsNarrow, useIsPhone } from "@/lib/useMediaQuery";
import { useRecording } from "@/lib/useRecording";
import { restorePreviousMotion } from "@/lib/motion";

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
  idlePaused,
  compact,
}: {
  recording: boolean;
  paused: boolean;
  idlePaused: boolean;
  compact: boolean;
}) {
  const state = !recording ? "idle" : paused ? "paused" : "recording";
  const label = !recording ? "未录制" : idlePaused ? "空闲暂停" : paused ? "已暂停" : "录制中";

  return (
    <div className="df-rec-status" data-compact={compact ? "true" : "false"}
      data-state={state} title={compact ? label : undefined} role="status">
      <span aria-hidden className="df-rec-dot" />
      <span key={state} className={compact ? "u-sr-only" : "df-feedback"}>{label}</span>
    </div>
  );
}

export function Shell({
  page,
  onPage,
  onError,
  recordingControl,
  children,
}: {
  page: PageKey;
  onPage: (p: PageKey) => void;
  onError?: (msg: string | null) => void;
  recordingControl: ReturnType<typeof useRecording>;
  children: ReactNode;
}) {
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
  const themeVersion = useRef(0);
  const themeWrites = useRef<Promise<unknown>>(Promise.resolve());

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("dayflow-theme", theme);
  }, [theme]);

  useEffect(() => {
    if (themeTouched.current) return;
    api
      .getSettings()
      .then((s) => {
        restorePreviousMotion(s.reduce_motion);
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
    const version = ++themeVersion.current;
    themeWrites.current = themeWrites.current.then(() => {
      if (version === themeVersion.current) return api.saveSettings({ theme: next });
    }).catch((error) => {
      if (version === themeVersion.current) {
        onError?.(error instanceof ApiError ? error.message : "主题未能保存，请重试");
      }
    });
  };

  const { state: rec, pending, run } = recordingControl;
  const recording = rec?.isRecording ?? false;
  const paused = rec?.isPaused || rec?.isIdlePaused || false;
  const action = recording ? (paused ? "resume" : "pause") : "start";
  const actionLabel = recording ? (paused ? "继续录制" : "暂停录制")
    : rec?.needsSetup ? "连接分析模型" : "开始录制";

  const phone = useIsPhone();
  const rail = useIsNarrow();
  /* 手机上不再有侧边栏，导航变成底部标签栏 */
  const collapsed = rail && !phone;

  const mainAction = (
    <Button variant="primary" fullWidth={!collapsed && !phone} size={phone ? "lg" : "md"}
      onClick={() => run(action)} loading={pending === action} disabled={pending !== null && pending !== action}
      title={actionLabel} aria-label={actionLabel}>
      {collapsed ? (recording && !paused ? "Ⅱ" : "▶") : actionLabel}
    </Button>
  );

  const stopAction = recording && (
    <Button fullWidth={!collapsed && !phone} size="sm" onClick={() => run("stop")}
      loading={pending === "stop"} disabled={pending !== null && pending !== "stop"}
      title="停止录制" aria-label="停止录制">
      {collapsed ? "■" : "停止录制"}
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

          <RecordingStatus recording={recording} paused={paused} idlePaused={!!rec?.isIdlePaused} compact={collapsed} />

          {mainAction}
          {stopAction}

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

        {/* 手机端：主操作在底部拇指区，导航在它下面 */}
        {phone && (
          <div className="df-phone-dock">
            <div className="df-mobile-recording">
              <RecordingStatus recording={recording} paused={paused} idlePaused={!!rec?.isIdlePaused} compact />
              {mainAction}
              {stopAction}
            </div>
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
