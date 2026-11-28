import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { PageKey, Shell } from "@/components/Shell";
import { TimelinePage } from "@/pages/TimelinePage";
import { StatsPage } from "@/pages/StatsPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { useRecording } from "@/lib/useRecording";
import { api } from "@/lib/api";
import { isToday, todayStr } from "@/lib/format";
import { Button, Spinner, Toast } from "@/components/ui";
import { LineIcon } from "@/components/LineIcon";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { CommandAction, CommandPalette } from "@/components/CommandPalette";
import { useExit } from "@/lib/motion";

export default function App() {
  const [page, setPage] = useState<PageKey>("timeline");
  const [date, setDate] = useState(todayStr());
  const [reportDate, setReportDate] = useState<{ day: string } | null>(null);
  const [activityFocus, setActivityFocus] = useState<{ day: string; id: number } | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [errorClosing, setErrorClosing] = useState(false);
  const errorToastRef = useRef<HTMLDivElement>(null);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [cmdClosing, setCmdClosing] = useState(false);
  const themeToggleRef = useRef<(() => void) | null>(null);
  const [bridgeReady, setBridgeReady] = useState(false);
  const [initError, setInitError] = useState<string | null>(null);

  const [attempt, setAttempt] = useState(0);
  const [seen, setSeen] = useState({ stats: false, reports: false, settings: false });
  const [setupRequest, setSetupRequest] = useState(0);

  const reportError = useCallback((msg: string | null) => {
    if (msg) {
      setErrorClosing(false);
      setStartError(msg);
    } else {
      setErrorClosing(true);
    }
  }, []);

  useExit(errorToastRef, errorClosing, () => {
    setStartError(null);
    setErrorClosing(false);
  });

  const go = useCallback((next: PageKey) => {
    if (next === "stats" || next === "reports" || next === "settings") {
      setSeen((previous) => (previous[next] ? previous : { ...previous, [next]: true }));
    }
    setPage(next);
  }, []);

  const openModelSettings = useCallback(() => {
    reportError(null);
    setSetupRequest((previous) => previous + 1);
    go("settings");
    if (isTauri()) {
      void invoke("show_main_window").catch(() => {});
    }
  }, [go, reportError]);

  const recordingControl = useRecording(bridgeReady, reportError, openModelSettings);

  useEffect(() => {
    if (!bridgeReady) return;
    const onGlobalKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k" && !e.repeat) {
        if (document.querySelector(".df-dialog") && !cmdOpen) return;
        e.preventDefault();
        if (cmdOpen && !cmdClosing) {
          setCmdClosing(true);
        } else {
          setCmdClosing(false);
          setCmdOpen(true);
        }
      }
    };
    window.addEventListener("keydown", onGlobalKey);
    return () => window.removeEventListener("keydown", onGlobalKey);
  }, [bridgeReady, cmdOpen, cmdClosing]);

  const commandActions = useMemo<CommandAction[]>(() => {
    const rec = recordingControl.state;
    const local = rec?.recordingMode !== "visual";
    const recording = rec?.isRecording ?? false;
    const paused = rec?.isPaused || rec?.isIdlePaused || false;
    const verb = local ? "计时" : "录制";
    const mainAction = recording ? (paused ? "resume" : "pause") : "start";
    const mainLabel = recording ? `${paused ? "继续" : "暂停"}${verb}`
      : rec?.needsSetup ? "连接分析模型" : `开始${verb}`;

    return [
      {
        id: "nav-timeline",
        group: "工作区导航",
        label: "前往时间轴",
        hint: "查看当日活动与时间分布",
        keywords: "timeline activities 活动 记录",
        icon: "clock",
        onSelect: () => go("timeline"),
      },
      {
        id: "nav-reports",
        group: "工作区导航",
        label: "前往日报",
        hint: "阅读本机总结与 AI 补充",
        keywords: "reports daily summary 总结",
        icon: "file",
        onSelect: () => { setReportDate({ day: date }); go("reports"); },
      },
      {
        id: "nav-stats",
        group: "工作区导航",
        label: "前往统计",
        hint: "趋势、类别占比与应用排行",
        keywords: "stats analytics 趋势 图表",
        icon: "chart",
        onSelect: () => go("stats"),
      },
      {
        id: "nav-settings",
        group: "工作区导航",
        label: "前往设置",
        hint: "模型连接、记录模式、外观与存储",
        keywords: "settings preferences 配置",
        icon: "settings",
        onSelect: () => go("settings"),
      },
      {
        id: "rec-primary",
        group: "计时与录制",
        label: mainLabel,
        hint: local ? "本机事件驱动，不截屏" : "截图分析模式",
        keywords: "start pause resume record timer 开始 暂停 继续",
        icon: recording && !paused ? "pause" : "play",
        disabled: recordingControl.pending !== null,
        onSelect: () => { void recordingControl.run(mainAction); },
      },
      {
        id: "rec-stop",
        group: "计时与录制",
        label: `停止${verb}`,
        hint: "保存当前活动并结束本轮记录",
        keywords: "stop end 停止 结束",
        icon: "stop",
        disabled: !recording || recordingControl.pending !== null,
        onSelect: () => { void recordingControl.run("stop"); },
      },
      {
        id: "quick-today",
        group: "快捷操作",
        label: "回到今天",
        hint: todayStr(),
        keywords: "today date 今天 日期",
        icon: "calendar",
        disabled: page === "timeline" && isToday(date),
        onSelect: () => { setDate(todayStr()); go("timeline"); },
      },
      {
        id: "quick-theme",
        group: "快捷操作",
        label: "切换浅色 / 深色主题",
        hint: "即时切换并保存到设置",
        keywords: "theme dark light 暗色 亮色 外观",
        icon: "sun",
        onSelect: () => themeToggleRef.current?.(),
      },
      {
        id: "quick-model",
        group: "快捷操作",
        label: "配置分析模型",
        hint: "直达 API 地址与密钥设置",
        keywords: "model api key openai ollama 模型",
        icon: "sparkles",
        onSelect: openModelSettings,
      },
    ];
  }, [date, go, openModelSettings, page, recordingControl]);

  useEffect(() => {
    let cancelled = false;
    let timer: number;
    const deadline = Date.now() + 16_000;
    const tick = async () => {
      try {
        await api.health(1500);
        if (!cancelled) setBridgeReady(true);
      } catch {
        if (cancelled) return;
        if (Date.now() < deadline) timer = window.setTimeout(tick, 400);
        else setInitError("Dayflow 本地服务未能启动。请重试，或退出后重新打开。");
      }
    };
    setInitError(null);
    void tick();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [attempt]);

  if (!bridgeReady) {
    if (initError) {
      return (
        <div
          className="df-page-in-soft"
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            height: "100vh",
            padding: "var(--space-6)",
            background: "var(--bg-canvas)",
            color: "var(--text-primary)",
          }}
        >
          <div style={{ textAlign: "center", maxWidth: 400 }}>
            <div
              style={{
                display: "inline-flex",
                color: "var(--danger)",
                marginBottom: "var(--space-4)",
              }}
              aria-hidden
            >
              <LineIcon name="alert" size={38} />
            </div>
            <h2
              style={{
                fontSize: "var(--text-xl)",
                fontWeight: "var(--weight-semibold)",
                marginBottom: "var(--space-2)",
              }}
            >
              启动失败
            </h2>
            <p
              style={{
                fontSize: "var(--text-sm)",
                color: "var(--text-tertiary)",
                marginBottom: "var(--space-5)",
              }}
            >
              {initError}
            </p>
            <Button variant="primary" onClick={() => setAttempt((previous) => previous + 1)}>
              重试
            </Button>
          </div>
        </div>
      );
    }
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          background: "var(--bg-canvas)",
          color: "var(--text-primary)",
        }}
      >
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: "var(--radius-md)",
            background: "var(--accent)",
            color: "var(--text-on-accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "var(--space-4)",
          }}
          aria-hidden
        >
          <LineIcon name="clock" size={24} />
        </div>
        <div
          role="status"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-3)",
            color: "var(--text-tertiary)",
            fontSize: "var(--text-sm)",
          }}
        >
          <Spinner size={14} />
          <span>正在启动本地服务…</span>
        </div>
      </div>
    );
  }

  return (
    <div style={{ height: "100%" }}>
      <Shell
        page={page}
        onPage={go}
        onError={reportError}
        onOpenCommandPalette={() => { setCmdClosing(false); setCmdOpen(true); }}
        themeToggleRef={themeToggleRef}
        recordingControl={recordingControl}
      >
        <div className="df-page" hidden={page !== "timeline"}>
          <ErrorBoundary label="时间轴">
            <TimelinePage
              date={date}
              active={page === "timeline"}
              onDateChange={setDate}
              activityFocus={activityFocus}
              onOpenReports={() => { setReportDate({ day: date }); go("reports"); }}
              recordingControl={recordingControl}
            />
          </ErrorBoundary>
        </div>

        {seen.stats && (
          <div className="df-page" hidden={page !== "stats"}>
            <ErrorBoundary label="统计">
              <StatsPage active={page === "stats"} />
            </ErrorBoundary>
          </div>
        )}

        {seen.reports && (
          <div className="df-page" hidden={page !== "reports"}>
            <ErrorBoundary label="日报">
              <ReportsPage
                initialDate={reportDate}
                active={page === "reports"}
                onSetupModel={openModelSettings}
                onOpenTimeline={(day, id) => {
                  setActivityFocus(id === undefined ? null : { day, id });
                  setDate(day);
                  go("timeline");
                }}
              />
            </ErrorBoundary>
          </div>
        )}

        {seen.settings && (
          <div className="df-page" hidden={page !== "settings"}>
            <ErrorBoundary label="设置">
              <SettingsPage
                active={page === "settings"}
                setupRequest={setupRequest}
                isRecording={recordingControl.state?.isRecording ?? false}
              />
            </ErrorBoundary>
          </div>
        )}

        {cmdOpen && (
          <CommandPalette
            open={!cmdClosing}
            onClose={() => setCmdClosing(true)}
            onExited={() => { setCmdOpen(false); setCmdClosing(false); }}
            actions={commandActions}
          />
        )}

        {startError && (
          <Toast
            ref={errorToastRef}
            variant="danger"
            position="top"
            closing={errorClosing}
            icon={<LineIcon name="alert" size={16} />}
            action={
              <Button size="sm" variant="ghost" onClick={() => setErrorClosing(true)} disabled={errorClosing}>
                关闭
              </Button>
            }
          >
            {startError}
          </Toast>
        )}
      </Shell>
    </div>
  );
}
