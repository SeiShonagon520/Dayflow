import { useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { api, ApiError, RecordingState } from "./api";
import { useLatest } from "./useLatest";

type Action = "start" | "stop" | "pause" | "resume";

export function useRecording(ready: boolean, onError: (message: string | null) => void, onSetup: () => void) {
  const [state, setState] = useState<RecordingState | null>(null);
  const [pending, setPending] = useState<Action | null>(null);
  const lock = useRef(false);
  const readId = useRef(0);

  const refresh = async () => {
    const id = ++readId.current;
    try {
      const current = await api.getRecordingState();
      if (id === readId.current) setState(current);
      return current;
    } catch {
      return null;
    }
  };

  const run = async (action: Action) => {
    if (lock.current) return;
    lock.current = true;
    onError(null);
    setPending(action);
    ++readId.current;
    try {
      if (action === "start") {
        if ((await refresh())?.needsSetup) {
          onSetup();
          return;
        }
        await api.startRecording();
      } else if (action === "stop") await api.stopRecording();
      else if (action === "pause") await api.pauseRecording();
      else await api.resumeRecording();
      await refresh();
    } catch (error) {
      if (action === "start" && error instanceof ApiError && error.status === 412) onSetup();
      else onError(error instanceof Error ? error.message : "录制操作失败");
    } finally {
      lock.current = false;
      setPending(null);
    }
  };

  const trayAction = useLatest((action: string) => {
    if (action === "quit-error") {
      onError("退出前未能确认最终保存，请在托盘重试退出。");
      return;
    }
    if (action === "start" || action === "stop") return run(action);
    if (action === "pause" && state?.isRecording) {
      return run(state.isPaused || state.isIdlePaused ? "resume" : "pause");
    }
  });

  useEffect(() => {
    if (!ready) return;
    let disposed = false;
    let unlisten: (() => void) | undefined;
    void refresh();
    const timer = window.setInterval(() => { if (!lock.current) void refresh(); }, 3000);
    listen<string[]>("tray-action", ({ payload: [kind, action] }) => {
      if (kind === "tray") void trayAction.current(action);
    }).then((cleanup) => {
      if (disposed) cleanup();
      else unlisten = cleanup;
    }).catch(() => {});
    return () => {
      disposed = true;
      ++readId.current;
      window.clearInterval(timer);
      unlisten?.();
    };
  }, [ready, trayAction]);

  return { state, pending, run };
}
