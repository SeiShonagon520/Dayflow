import { useEffect, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { PageKey, Shell } from "@/components/Shell";
import { TimelinePage } from "@/pages/TimelinePage";
import { StatsPage } from "@/pages/StatsPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { useRecording } from "@/lib/useRecording";
import { api } from "@/lib/api";
import { todayStr } from "@/lib/format";
import { Button } from "@/components/ui";
import { ErrorBoundary } from "@/components/ErrorBoundary";

export default function App() {
  const [page, setPage] = useState<PageKey>("timeline");
  const [date, setDate] = useState(todayStr());
  const [reportDate, setReportDate] = useState<{ day: string } | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [bridgeReady, setBridgeReady] = useState(false);
  const [initError, setInitError] = useState<string | null>(null);

  const [attempt, setAttempt] = useState(0);
  const [seen, setSeen] = useState({ reports: false, settings: false });
  const [setupRequest, setSetupRequest] = useState(0);

  const go = (next: PageKey) => {
    if (next === "reports" || next === "settings") {
      setSeen((previous) => ({ ...previous, [next]: true }));
    }
    setPage(next);
  };

  const recordingControl = useRecording(bridgeReady, setStartError, () => {
    setStartError(null);
    setSetupRequest((previous) => previous + 1);
    go("settings");
    if (isTauri()) {
      void invoke("show_main_window").catch(() => {});
    }
  });

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
        else setInitError("Dayflow 后台未能启动。请重试，或退出 Dayflow 后重新打开。");
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
            <div style={{ fontSize: 40, marginBottom: "var(--space-4)" }}>⚠️</div>
            <h2
              style={{
                fontSize: "var(--text-xl)",
                fontWeight: "var(--weight-semibold)",
                marginBottom: "var(--space-2)",
              }}
            >
              加载失败
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
            color: "var(--on-accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 24,
            marginBottom: "var(--space-4)",
          }}
        >
          ◷
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-3)",
            color: "var(--text-tertiary)",
            fontSize: "var(--text-sm)",
          }}
        >
          <span
            className="df-spin"
            style={{
              display: "inline-block",
              width: 14,
              height: 14,
              border: "2px solid var(--border-strong)",
              borderRightColor: "transparent",
              borderRadius: "50%",
            }}
          />
          <span>正在连接服务...</span>
        </div>
      </div>
    );
  }

  return (
    <Shell page={page} onPage={go} onError={setStartError} recordingControl={recordingControl}>
      <div className="df-page" hidden={page !== "timeline"}>
        <ErrorBoundary label="时间轴">
          <TimelinePage date={date} active={page === "timeline"} onDateChange={setDate}
            onOpenReports={() => { setReportDate({ day: date }); go("reports"); }}
            recordingControl={recordingControl} />
        </ErrorBoundary>
      </div>

      {page === "stats" && (
        <div className="df-page"><ErrorBoundary label="统计"><StatsPage /></ErrorBoundary></div>
      )}

      {seen.reports && (
        <div className="df-page" hidden={page !== "reports"}>
          <ErrorBoundary label="日报">
            <ReportsPage initialDate={reportDate} active={page === "reports"}
              onOpenTimeline={(day) => { setDate(day); go("timeline"); }} />
          </ErrorBoundary>
        </div>
      )}

      {seen.settings && (
        <div className="df-page" hidden={page !== "settings"}>
          <ErrorBoundary label="设置">
            <SettingsPage setupRequest={setupRequest} isRecording={recordingControl.state?.isRecording ?? false} />
          </ErrorBoundary>
        </div>
      )}

      {startError && (
        <div
          role="alert"
          className="df-feedback"
          style={{
            position: "fixed",
            bottom: "var(--space-6)",
            left: "50%",
            transform: "translateX(-50%)",
            display: "flex",
            alignItems: "center",
            gap: "var(--space-3)",
            padding: "var(--space-3) var(--space-4)",
            background: "var(--danger-bg)",
            border: "1px solid var(--danger)",
            borderRadius: "var(--radius-md)",
            color: "var(--danger)",
            fontSize: "var(--text-sm)",
            zIndex: "var(--z-toast)",
          }}
        >
          <span>{startError}</span>
          <Button size="sm" variant="ghost" onClick={() => setStartError(null)}>
            知道了
          </Button>
        </div>
      )}
    </Shell>
  );
}
