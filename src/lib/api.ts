/*
 * 后端 API 客户端
 *
 * 单独一层，而不是在组件里直接 fetch。原因：
 *   · 端口号只出现在这一个文件
 *   · 错误处理统一（后端返回中文错误信息，直接透传给用户）
 *   · 类型集中，改后端时编译期就能发现前端用错了
 */

import { invoke } from "@tauri-apps/api/core";

// 开发时前端跑在 Vite 上，后端是独立进程；
// 打包后由 Tauri 启动 bridge，仍走同一端口。
const BASE = "http://127.0.0.1:8899";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

/* 默认超时。之前没有任何超时：后端 hang 住（分析卡死、端口被占但不响应）
   时 fetch 永不返回，界面上的转圈会转到用户杀进程为止。
   普通读写 15 秒足够；慢的那几个在下面各自放宽。 */
const DEFAULT_TIMEOUT_MS = 15_000;

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
  retries: number = 2
): Promise<T> {
  /* AbortSignal.timeout 需要 Chrome 103+。打包目标是 chrome105
     （Win10 的 WebView2），够用。 */
  const signal = AbortSignal.timeout(timeoutMs);

  let resp: Response;
  try {
    resp = await fetch(`${BASE}${path}`, {
      ...init,
      signal,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (e) {
    /* 超时和连不上是两回事，得分开说：
       连不上要重启，超时往往是后台正忙（在跑分析、在等 AI）。 */
    if (e instanceof DOMException && e.name === "TimeoutError") {
      throw new ApiError(
        `后台 ${Math.round(timeoutMs / 1000)} 秒没有响应，` +
        "可能正在处理其它任务，稍后再试",
        408
      );
    }
    // 当 bridge 刚启动尚未就绪时（PyInstaller 解压需 1~2 秒），自动稍作等待并重试
    if (retries > 0 && (!init?.method || init.method === "GET")) {
      await new Promise((r) => setTimeout(r, 600));
      return request<T>(path, init, timeoutMs, retries - 1);
    }
    // fetch 抛错通常是 bridge 没起来
    throw new ApiError("无法连接后台服务，请重启 Dayflow", 0);
  }

  if (!resp.ok) {
    let detail = `请求失败（${resp.status}）`;
    try {
      const body = await resp.json();
      if (body?.detail) {
        detail = typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
      }
    } catch {
      /* 响应不是 JSON，用默认文案 */
    }
    throw new ApiError(detail, resp.status);
  }

  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

// ── 类型 ──────────────────────────────────────────────────

export interface AppSite {
  name: string;
  durationSeconds: number;
  iconUrl: string | null;
}

export interface Distraction {
  description: string;
  timestamp: number;
  durationSeconds: number;
}

export interface ActivityCard {
  id: number;
  category: string;
  title: string;
  summary: string;
  startTime: string | null;
  endTime: string | null;
  durationMinutes: number;
  productivityScore: number;
  appSites: AppSite[];
  distractions: Distraction[];
}

export interface Stats {
  days: number;
  rangeStart: string;
  rangeEnd: string;
  metrics: {
    totalHours: number;
    avgScore: number;
    deepWork: number;
    activityCount: number;
    todayHours: number;
    todayScore: number;
  };
  changes: {
    totalHours: number;
    avgScore: number;
    deepWork: number;
    activityCount: number;
  };
  categories: { name: string; minutes: number }[];
  trend: { date: string; score: number; hours: number }[];
  daily: { date: string; categories: Record<string, number> }[];
  hourly: { score: number; minutes: number }[][];
  calendar: { date: string; hours: number; score: number; count: number }[];
  appRanking: { name: string; minutes: number }[];
}

export interface RecordingState {
  isRecording: boolean;
  isPaused: boolean;
  isIdlePaused: boolean;
}

export interface Settings {
  api_url: string;
  api_key: string;
  api_key_configured: boolean;
  api_model: string;
  theme: string;
  daily_goal: string;
  idle_pause_enabled: string;
  idle_pause_timeout_min: string;
  record_output_idx: string;
  chunks_max_size_gb: string;
  custom_chunks_dir: string;
  email_enabled: string;
  email_sender: string;
  email_auth_code: string;
  email_receiver: string;
  email_send_times: string;
  [key: string]: string | boolean;
}

/* 把后端返回的活动记录归一化成 ActivityCard 承诺的形状。

   为什么在这一层做，而不是在渲染处逐个防：
   同一个坑已经踩过三次 —— dates.length、cards.length、metrics 各补了一遍，
   结果 appSites.slice 和 title.toLowerCase 又崩了两次。散在各处的
   `x || ""` 只会漏，而且崩溃点离缺陷点很远（title 为 null 时页面是好的，
   用户一搜索才炸），最难归因。

   出口只有一处，补一次就够。 */
function normalizeCard(raw: unknown): ActivityCard {
  const c = (raw ?? {}) as Partial<ActivityCard>;
  return {
    id: typeof c.id === "number" ? c.id : 0,
    category: c.category ?? "其他",
    title: c.title ?? "",
    summary: c.summary ?? "",
    startTime: c.startTime ?? null,
    endTime: c.endTime ?? null,
    durationMinutes:
      typeof c.durationMinutes === "number" && Number.isFinite(c.durationMinutes)
        ? c.durationMinutes
        : 0,
    productivityScore:
      typeof c.productivityScore === "number" &&
      Number.isFinite(c.productivityScore)
        ? c.productivityScore
        : 0,
    /* 这两个是嵌套数组：少了它们，slice / map 会直接抛。 */
    appSites: (Array.isArray(c.appSites) ? c.appSites : []).map((a) => ({
      name: a?.name ?? "",
      durationSeconds:
        typeof a?.durationSeconds === "number" ? a.durationSeconds : 0,
      iconUrl: a?.iconUrl ?? null,
    })),
    distractions: (Array.isArray(c.distractions) ? c.distractions : []).map(
      (d) => ({
        description: d?.description ?? "",
        timestamp: typeof d?.timestamp === "number" ? d.timestamp : 0,
        durationSeconds:
          typeof d?.durationSeconds === "number" ? d.durationSeconds : 0,
      })
    ),
  };
}

// ── 接口 ──────────────────────────────────────────────────

export const api = {
  health: () => request<{ ok: boolean; version: string }>("/api/health"),

  getCards: async (date: string): Promise<{ cards: ActivityCard[] }> => {
    const res = await request<{ cards: unknown }>(`/api/cards/${date}`);
    return {
      cards: (Array.isArray(res?.cards) ? res.cards : []).map(normalizeCard),
    };
  },

  updateCard: (id: number, patch: Partial<ActivityCard>) =>
    request<{ ok: boolean }>(`/api/cards/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        category: patch.category,
        title: patch.title,
        summary: patch.summary,
        productivityScore: patch.productivityScore,
      }),
    }),

  deleteCard: (id: number) =>
    request<{ ok: boolean }>(`/api/cards/${id}`, { method: "DELETE" }),

  restoreCard: (card: ActivityCard) =>
    request<{ ok: boolean }>("/api/cards/restore", {
      method: "POST",
      body: JSON.stringify({ card }),
    }),

  /* 统计要聚合整段区间的记录，比普通读表慢，放宽到 30 秒。 */
  getStats: (days: 7 | 30) =>
    request<Stats>(`/api/stats?days=${days}`, undefined, 30_000),

  getRecordingState: () => request<RecordingState>("/api/recording/state"),

  startRecording: () =>
    request<{ ok: boolean }>("/api/recording/start", { method: "POST" }),

  stopRecording: () =>
    request<{ ok: boolean }>("/api/recording/stop", { method: "POST" }),

  pauseRecording: () =>
    request<{ ok: boolean }>("/api/recording/pause", { method: "POST" }),

  resumeRecording: () =>
    request<{ ok: boolean }>("/api/recording/resume", { method: "POST" }),

  getProgress: () =>
    request<{ pending: number; analyzing: boolean }>("/api/analysis/progress"),

  getSettings: () => request<Settings>("/api/settings/all"),

  saveSettings: (values: Record<string, string>) =>
    request<{ ok: boolean }>("/api/settings", {
      method: "POST",
      body: JSON.stringify({ values }),
    }),

  /* 这几个都要出公网或等模型回话，不能用 15 秒的默认值。
     超时报错文案里带的秒数取自这里，所以数值和文案是一套。 */

  // 连通性测试要真的打一次模型接口
  testConnection: () =>
    request<{ ok: boolean; message: string }>("/api/test/connection", {
      method: "POST",
    }, 30_000),

  getReportDates: () =>
    request<{ dates: string[] }>("/api/reports/dates"),

  getReport: (date: string) =>
    request<{ date: string; content: string }>(`/api/reports/${date}`),

  // 生成日报要把一天的记录喂给模型，分钟级。给 5 分钟，
  // 宁可让它慢，也不要生成到一半被判超时 —— 那样最浪费。
  generateReport: (date: string) =>
    request<{ date: string; content: string }>(`/api/reports/${date}`, {
      method: "POST",
    }, 300_000),

  getAutostart: () =>
    request<{ enabled: boolean; stale: boolean }>("/api/autostart"),

  setAutostart: (enable: boolean) =>
    request<{ ok: boolean; message: string }>(
      `/api/autostart/${enable ? "enable" : "disable"}`,
      { method: "POST" }
    ),

  checkUpdate: () =>
    request<{
      hasUpdate: boolean;
      currentVersion: string;
      latestVersion: string;
      downloadUrl: string;
      notes: string;
      fileSize: number;
    }>("/api/update/check", undefined, 30_000),

  getStorageInfo: () =>
    request<{
      chunksDir: string;
      usedBytes: number;
      usedMb: number;
      limitGb: number;
      percent: number;
      dataDir: string;
    }>("/api/storage/info"),

  setCacheLimit: (gb: number) =>
    request<{ ok: boolean; limitGb: number }>("/api/storage/cache-limit", {
      method: "POST",
      body: JSON.stringify({ gb }),
    }),

  // 清缓存是批量删文件，可能慢
  clearChunks: () =>
    request<{ ok: boolean; removed: number }>("/api/storage/clear-chunks", {
      method: "POST",
    }, 60_000),

  getCsv: (date: string) => request<string>(`/api/export/csv/${date}`),
};

/**
 * 写文件到磁盘（导出用）。走 Tauri 的文件系统能力。
 * 浏览器直接下载在 Tauri 里会被拦截，所以必须走原生。
 */
export async function saveTextFile(
  defaultName: string,
  content: string,
  ext: string
): Promise<string | null> {
  return invoke<string | null>("save_text_file", {
    defaultName,
    content,
    ext,
  });
}
