/*
 * 应用外壳
 *
 * 侧边栏在三个阶段之间切换，依据是内容还剩多少可用宽度：
 *   ≥1000px  完整侧栏，图标 + 文字
 *   ≥620px   图标栏 56px，只留图标，文字转 tooltip
 *   <620px   底部标签栏，导航移到拇指区，主操作留在底部
 */

import { MutableRefObject, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { Button, IconSwap, Kbd, Tooltip } from "@/components/ui";
import { LineIcon, LineIconName } from "@/components/LineIcon";
import { useIsNarrow, useIsPhone } from "@/lib/useMediaQuery";
import { useRecording } from "@/lib/useRecording";
import { restorePreviousMotion } from "@/lib/motion";
import { readTheme } from "@/lib/theme";

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
  const button = (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? item.label : undefined}
      className={`df-nav-item${active ? " is-active" : ""}`}
      data-collapsed={collapsed ? "true" : "false"}
      style={{ width: collapsed ? 40 : "100%" }}
    >
      <span aria-hidden style={{ width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <LineIcon name={item.icon} />
      </span>
      <span className="df-nav-label" aria-hidden={collapsed || undefined}>
        {item.label}
      </span>
    </button>
  );

  return collapsed ? (
    <Tooltip content={item.label} placement="right">
      {button}
    </Tooltip>
  ) : button;
}

function RecordingStatus({
  recording,
  paused,
  idlePaused,
  privacyPaused,
  local,
  compact,
}: {
  recording: boolean;
  paused: boolean;
  idlePaused: boolean;
  privacyPaused: boolean;
  local: boolean;
  compact: boolean;
}) {
  const state = !recording ? "idle" : paused || privacyPaused ? "paused" : "recording";
  const label = !recording ? (local ? "本机计时" : "截图分析")
    : idlePaused ? "空闲暂停" : paused ? "已暂停" : privacyPaused ? "隐私暂停" : local ? "本机计时中" : "录制中";

  const statusNode = (
    <div
      className="df-rec-status"
      data-compact={compact ? "true" : "false"}
      data-state={state}
      role="status"
    >
      <span aria-hidden className="df-rec-dot" />
      <span key={label} className={compact ? "u-sr-only" : "df-feedback"}>{label}</span>
    </div>
  );

  return compact ? (
    <Tooltip content={label} placement="right">
      {statusNode}
    </Tooltip>
  ) : statusNode;
}

export function Shell({
  page,
  onPage,
  onError,
  onOpenCommandPalette,
  themeToggleRef,
  recordingControl,
  children,
}: {
  page: PageKey;
  onPage: (p: PageKey) => void;
  onError?: (msg: string | null) => void;
  onOpenCommandPalette?: () => void;
  themeToggleRef?: MutableRefObject<(() => void) | null>;
  recordingControl: ReturnType<typeof useRecording>;
  children: ReactNode;
}) {
  const [theme, setTheme] = useState(readTheme);
  const themeTouched = useRef(false);
  const themeVersion = useRef(0);
  const themeWrites = useRef<Promise<unknown>>(Promise.resolve());
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

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
        /* 后端未就绪时保留 localStorage 主题 */
      });
  }, []);

  const toggleTheme = useCallback(() => {
    themeTouched.current = true;
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      const version = ++themeVersion.current;
      themeWrites.current = themeWrites.current.then(() => {
        if (version === themeVersion.current) return api.saveSettings({ theme: next });
      }).catch((error) => {
        if (version === themeVersion.current) {
          onErrorRef.current?.(error instanceof ApiError ? error.message : "主题未能保存，请重试");
        }
      });
      return next;
    });
  }, []);

  useEffect(() => {
    if (!themeToggleRef) return;
    themeToggleRef.current = toggleTheme;
    return () => { themeToggleRef.current = null; };
  }, [themeToggleRef, toggleTheme]);

  const { state: rec, pending, run } = recordingControl;
  const local = rec?.recordingMode !== "visual";
  const recording = rec?.isRecording ?? false;
  const paused = rec?.isPaused || rec?.isIdlePaused || false;
  const action = recording ? (paused ? "resume" : "pause") : "start";
  const verb = local ? "计时" : "录制";
  const actionLabel = recording ? `${paused ? "继续" : "暂停"}${verb}`
    : rec?.needsSetup ? "连接分析模型" : `开始${verb}`;

  const phone = useIsPhone();
  const rail = useIsNarrow();
  const collapsed = rail && !phone;

  const mainIcon = (
    <IconSwap
      active={recording && !paused}
      size={15}
      first={<LineIcon name="play" size={14} />}
      second={<LineIcon name="pause" size={14} />}
    />
  );

  const mainActionButton = (
    <Button
      variant="primary"
      fullWidth={!collapsed && !phone}
      size={phone ? "lg" : "md"}
      onClick={() => run(action)}
      loading={pending === action}
      disabled={pending !== null && pending !== action}
      aria-label={actionLabel}
    >
      {mainIcon}
      {!collapsed && <span>{actionLabel}</span>}
    </Button>
  );

  const mainAction = collapsed ? (
    <Tooltip content={actionLabel} placement="right">
      {mainActionButton}
    </Tooltip>
  ) : mainActionButton;

  const stopActionButton = (
    <div className="df-fade-up" style={{ width: !collapsed && !phone ? "100%" : undefined }}>
      <Button
        fullWidth={!collapsed && !phone}
        size="sm"
        onClick={() => run("stop")}
        loading={pending === "stop"}
        disabled={pending !== null && pending !== "stop"}
        aria-label={`停止${verb}`}
      >
        <LineIcon name="stop" size={13} />
        {!collapsed && !phone && <span>停止{verb}</span>}
      </Button>
    </div>
  );

  const stopAction = phone ? (
    <span style={{ visibility: recording ? undefined : "hidden" }}>
      {stopActionButton}
    </span>
  ) : recording && (
    collapsed ? (
      <Tooltip content={`停止${verb}`} placement="right">
        {stopActionButton}
      </Tooltip>
    ) : stopActionButton
  );

  const brand = (
    <div className="df-brand">
      <span aria-hidden className="df-brand-mark">
        <i />
        <i />
        <i />
      </span>
      <span className="df-brand-name" aria-hidden={collapsed || undefined}>Dayflow</span>
    </div>
  );

  const themeActionLabel = theme === "dark" ? "切换浅色" : "切换深色";
  const themeAriaLabel = theme === "dark" ? "切换到亮色" : "切换到暗色";

  const themeButton = (
    <Button
      variant="ghost"
      fullWidth={!collapsed && !phone}
      size="sm"
      onClick={toggleTheme}
      aria-label={themeAriaLabel}
    >
      <IconSwap
        active={theme === "dark"}
        size={15}
        first={<LineIcon name="moon" size={15} />}
        second={<LineIcon name="sun" size={15} />}
      />
      {!collapsed && !phone && <span>{themeActionLabel}</span>}
    </Button>
  );

  const commandButton = onOpenCommandPalette && (
    <button
      type="button"
      className="df-cmd-trigger"
      aria-label="打开快捷命令面板"
      aria-keyshortcuts="Control+K Meta+K"
      onClick={onOpenCommandPalette}
    >
      <span className="df-command-prompt" aria-hidden>&gt;_</span>
      <span className="df-cmd-trigger-text">快捷命令</span>
      <Kbd>Ctrl K</Kbd>
    </button>
  );

  return (
    <div
      className="df-shell"
      data-layout={phone ? "bottom" : collapsed ? "rail" : "full"}
    >
      {!phone && (
        <nav className="df-sidebar" aria-label="主导航">
          {brand}

          {commandButton && (
            collapsed ? (
              <Tooltip content="快捷命令 (Ctrl+K)" placement="right">
                {commandButton}
              </Tooltip>
            ) : commandButton
          )}

          {NAV.map((item) => (
            <NavItem
              key={item.key}
              item={item}
              active={page === item.key}
              collapsed={collapsed}
              onClick={() => onPage(item.key)}
            />
          ))}

          <div className="df-sidebar-footer">
            <div className="df-rec-panel">
              <RecordingStatus
                recording={recording}
                paused={paused}
                local={local}
                idlePaused={!!rec?.isIdlePaused}
                privacyPaused={!!rec?.isPrivacyPaused}
                compact={collapsed}
              />
              {mainAction}
              {stopAction}
            </div>

            {collapsed ? (
              <Tooltip content={themeActionLabel} placement="right">
                {themeButton}
              </Tooltip>
            ) : themeButton}
          </div>
        </nav>
      )}

      {/* ── 内容区 ─────────────────────────────────────── */}
      <main className="df-main">
        {children}

        {/* 手机端：主操作在底部拇指区，导航在它下面 */}
        {phone && (
          <div className="df-phone-dock">
            <div className="df-mobile-recording">
              <RecordingStatus
                recording={recording}
                paused={paused}
                local={local}
                idlePaused={!!rec?.isIdlePaused}
                privacyPaused={!!rec?.isPrivacyPaused}
                compact
              />
              {mainAction}
              {stopAction}
              {themeButton}
              {commandButton}
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
