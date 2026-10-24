import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { PageKey, Shell } from "@/components/Shell";
import { TimelinePage } from "@/pages/TimelinePage";
import { StatsPage } from "@/pages/StatsPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { api } from "@/lib/api";
import { todayStr } from "@/lib/format";
import { Button } from "@/components/ui";
import { ErrorBoundary } from "@/components/ErrorBoundary";

export default function App() {
  const [page, setPage] = useState<PageKey>("timeline");
  const [date, setDate] = useState(todayStr());
  const [startError, setStartError] = useState<string | null>(null);
  const [bridgeReady, setBridgeReady] = useState(false);
  const [initError, setInitError] = useState<string | null>(null);

  const checkBridge = () => {
    setInitError(null);
    let attempts = 0;
    const max = 40; // 40 * 400ms = 16s 缓冲期，足够 PyInstaller 解压并完成初始化
    const tick = async () => {
      try {
        await api.health();
        setBridgeReady(true);
      } catch {
        attempts++;
        if (attempts < max) {
          setTimeout(tick, 400);
        } else {
          setInitError("无法连接后台服务，请检查应用日志或重启 Dayflow");
        }
      }
    };
    tick();
  };

  useEffect(() => {
    checkBridge();
  }, []);

  // 从托盘点「开始录制 / 停止录制」时，Rust 侧会发这个事件
  useEffect(() => {
    let unlisten: (() => void) | undefined;
    (async () => {
      try {
        unlisten = await listen<string[]>("tray-action", (e) => {
          const [kind, action] = e.payload;
          if (kind !== "tray") return;
          if (action === "start") {
            api.startRecording().catch((err) => setStartError(String(err)));
          } else if (action === "stop") {
            api.stopRecording().catch(() => {});
          }
        });
      } catch {
        // 浏览器里跑（预览）时没有 Tauri runtime，忽略
      }
    })();
    return () => unlisten?.();
  }, []);

  const startRecording = async () => {
    setStartError(null);
    try {
      await api.startRecording();
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "启动录制失败");
    }
  };

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
            <Button variant="primary" onClick={checkBridge}>
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
    <Shell page={page} onPage={setPage} onError={setStartError}>
      {/* key={page} 强制重建 DOM 节点 —— React 默认复用同一节点，
          不换 key 的话切换页面时入场动画只会跑第一次。

          每个页面套一层错误边界：一个页面崩了，导航和窗口还在，
          用户还能切走。实测没有边界时，日报页一个 undefined.length
          就让 .df-shell 从 DOM 消失，整个窗口变白屏。 */}
      <div key={page} className="df-page">
        {page === "timeline" && (
          <ErrorBoundary label="时间轴">
            <TimelinePage
              date={date}
              onDateChange={setDate}
              onOpenReports={() => setPage("reports")}
              onStartRecording={startRecording}
            />
          </ErrorBoundary>
        )}
        {page === "stats" && (
          <ErrorBoundary label="统计">
            <StatsPage />
          </ErrorBoundary>
        )}
        {page === "reports" && (
          <ErrorBoundary label="日报">
            <ReportsPage />
          </ErrorBoundary>
        )}
        {page === "settings" && (
          <ErrorBoundary label="设置">
            <SettingsPage />
          </ErrorBoundary>
        )}
      </div>

      {startError && (
        <div
          role="alert"
          className="df-shake"
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
