import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Dialog } from "@/components/Dialog";
import { CommandPalette } from "@/components/CommandPalette";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { MotionControl } from "@/components/MotionControl";
import { Shell } from "@/components/Shell";
import { LoadingHandoff } from "@/components/LoadingHandoff";
import { Button, ChartPopover, IconSwap, NumberStepper, SegmentedControl, Toggle, Tooltip } from "@/components/ui";
import { CATEGORIES, categoryVar, formatMinutes } from "@/lib/format";
import { isReducedMotionActive } from "@/lib/motion";
import { api } from "@/lib/api";
import { TimelinePage } from "@/pages/TimelinePage";
import { ReportsPage } from "@/pages/ReportsPage";
import { StatsPage } from "@/pages/StatsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import type { useRecording } from "@/lib/useRecording";

type RecordingControl = ReturnType<typeof useRecording>;

afterEach(() => {
  cleanup();
  localStorage.clear();
  document.documentElement.removeAttribute("data-motion");
  document.documentElement.removeAttribute("data-theme");
  vi.restoreAllMocks();
});

function mockViewport(width: number) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => {
      const max = query.match(/max-width:\s*(\d+)px/);
      const matches = max ? width <= Number(max[1]) : false;
      return {
        matches,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      };
    },
  });
}

describe("Dialog accessibility and focus lifecycle", () => {
  it("marks .df-shell inert while mounted, traps Tab, closes on Escape, and restores focus", () => {
    const onClose = vi.fn();
    const onExited = vi.fn();
    const { rerender } = render(
      <div>
        <div className="df-shell">
          <button type="button">背景按钮</button>
        </div>
      </div>,
    );
    const trigger = screen.getByRole("button", { name: "背景按钮" });
    trigger.focus();

    rerender(
      <div>
        <div className="df-shell">
          <button type="button">背景按钮</button>
        </div>
        <Dialog open labelledBy="confirm-title" onClose={onClose} onExited={onExited}>
          <h2 id="confirm-title">确认操作</h2>
          <button type="button">第一个</button>
          <button type="button">第二个</button>
        </Dialog>
      </div>,
    );

    const shell = document.querySelector(".df-shell") as HTMLElement;
    expect(shell.hasAttribute("inert")).toBe(true);

    const dialog = screen.getByRole("dialog", { name: "确认操作" });
    const first = screen.getByRole("button", { name: "第一个" });
    const second = screen.getByRole("button", { name: "第二个" });
    Object.defineProperty(first, "offsetWidth", { value: 80, configurable: true });
    Object.defineProperty(second, "offsetWidth", { value: 80, configurable: true });

    second.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(first);

    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(second);

    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    rerender(
      <div>
        <div className="df-shell">
          <button type="button">背景按钮</button>
        </div>
      </div>,
    );
    expect(shell.hasAttribute("inert")).toBe(false);
    expect(document.activeElement).toBe(trigger);
  });
});

describe("MotionControl keyboard radiogroup", () => {
  it("supports arrow-key roving tabIndex and persists data-motion", () => {
    render(<MotionControl />);
    const group = screen.getByRole("radiogroup", { name: "界面动效强度" });
    const radios = screen.getAllByRole("radio");

    expect(radios[0]).toHaveAttribute("aria-checked", "true");
    expect(radios[0]).toHaveAttribute("tabIndex", "0");
    expect(radios[1]).toHaveAttribute("tabIndex", "-1");

    fireEvent.keyDown(group, { key: "ArrowRight" });
    expect(radios[1]).toHaveAttribute("aria-checked", "true");
    expect(radios[1]).toHaveAttribute("tabIndex", "0");
    expect(document.documentElement.getAttribute("data-motion")).toBe("reduced");
    expect(localStorage.getItem("dayflow-motion")).toBe("reduced");
  });
});

it("keeps the previous view visible but inoperable while switching content", () => {
  const { rerender } = render(
    <LoadingHandoff loading={false} retainOnReload skeleton={<p>骨架</p>}>
      <button>旧日期的活动</button>
    </LoadingHandoff>,
  );
  rerender(
    <LoadingHandoff loading retainOnReload skeleton={<p>骨架</p>}>
      <button>新日期的活动</button>
    </LoadingHandoff>,
  );
  expect(screen.getByText("旧日期的活动").closest("[inert]")).toHaveAttribute("aria-hidden", "true");
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(screen.getByText("正在读取…")).toBeVisible();
  rerender(
    <LoadingHandoff loading={false} retainOnReload skeleton={<p>骨架</p>}>
      <button>新日期的活动</button>
    </LoadingHandoff>,
  );
  expect(screen.getByRole("button", { name: "新日期的活动" }).closest("[inert]")).toBeNull();
});

describe("Shell responsive layout and rail mode controls", () => {
  const recordingControl: RecordingControl = {
    state: {
      recordingMode: "local",
      needsSetup: false,
      isRecording: false,
      isPaused: false,
      isIdlePaused: false,
      isPrivacyPaused: false,
    },
    pending: null,
    run: vi.fn(async () => {}),
  };

  it("renders visible glyphs for rail sidebar buttons and omits duplicate .df-focus-ring nodes", () => {
    mockViewport(800);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ theme: "light", reduce_motion: "system" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const { container } = render(
      <Shell page="timeline" onPage={vi.fn()} recordingControl={recordingControl}>
        <div>内容</div>
      </Shell>,
    );

    expect(container.querySelector(".df-shell")).toHaveAttribute("data-layout", "rail");
    const startButton = screen.getByRole("button", { name: "开始计时" });
    const themeButton = screen.getByRole("button", { name: "切换到暗色" });
    expect(startButton.querySelector(".df-icon-swap svg")).toBeInTheDocument();
    expect(themeButton.querySelector(".df-icon-swap svg")).toBeInTheDocument();
    expect(container.querySelectorAll(".df-focus-ring")).toHaveLength(0);
  });

  it("renders bottom navigation dock below 620px", () => {
    mockViewport(420);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ theme: "light", reduce_motion: "system" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const { container } = render(
      <Shell page="stats" onPage={vi.fn()} recordingControl={recordingControl}>
        <div>统计</div>
      </Shell>,
    );

    expect(container.querySelector(".df-shell")).toHaveAttribute("data-layout", "bottom");
    expect(container.querySelector(".df-phone-dock")).toBeInTheDocument();
  });
});

describe("ErrorBoundary and base UI primitives", () => {
  it("isolates page crashes and resets on retry click", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    let shouldThrow = true;
    function FlakyPage() {
      if (shouldThrow) throw new Error("boom");
      return <div>恢复成功</div>;
    }

    render(
      <ErrorBoundary label="统计页">
        <FlakyPage />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("统计页加载失败");
    const retry = screen.getByRole("button", { name: "重新载入" });
    expect(retry).toHaveAttribute("data-variant", "primary");

    shouldThrow = false;
    fireEvent.click(retry);
    expect(screen.getByText("恢复成功")).toBeInTheDocument();
    expect(consoleSpy).toHaveBeenCalled();
  });

  it("renders Button, Toggle, IconSwap, and SegmentedControl motion contracts cleanly", () => {
    const onToggle = vi.fn();
    const onBusyClick = vi.fn();
    const onSegmentChange = vi.fn();
    const { container, rerender } = render(
      <div>
        <Button variant="primary" loading onClick={onBusyClick}>保存</Button>
        <Toggle checked={false} onChange={onToggle} label="启用" />
        <IconSwap active={false} first={<span>A</span>} second={<span>B</span>} />
        <SegmentedControl
          label="统计周期"
          value="7"
          onChange={onSegmentChange}
          options={[
            { value: "7", label: "7 天" },
            { value: "14", label: "14 天" },
            { value: "30", label: "30 天" },
          ]}
        />
      </div>,
    );
    expect(container.querySelectorAll(".df-focus-ring")).toHaveLength(0);

    // Button busy state preserves label width while crossfading spinner and blocking clicks
    const busyBtn = screen.getByRole("button", { name: "保存" });
    expect(busyBtn).toHaveAttribute("aria-busy", "true");
    expect(busyBtn.querySelector(".df-button-label")).toHaveAttribute("data-hidden", "true");
    expect(busyBtn.querySelector(".df-busy-spinner")).toHaveAttribute("data-visible", "true");
    fireEvent.click(busyBtn);
    expect(onBusyClick).not.toHaveBeenCalled();

    // Toggle directional transform origin + click
    const toggle = screen.getByRole("switch", { name: "启用" });
    expect(toggle.querySelector("span")?.style.transformOrigin).toBe("left center");
    fireEvent.click(toggle);
    expect(onToggle).toHaveBeenCalledWith(true);

    // IconSwap state
    expect(container.querySelector(".df-icon-swap")).toHaveAttribute("data-swapped", "false");

    // SegmentedControl GPU sliding thumb index + arrow-key navigation
    const tablist = screen.getByRole("tablist", { name: "统计周期" });
    expect(tablist.style.getPropertyValue("--seg-count")).toBe("3");
    expect(tablist.style.getPropertyValue("--seg-index")).toBe("0");
    fireEvent.keyDown(tablist, { key: "ArrowRight" });
    expect(onSegmentChange).toHaveBeenCalledWith("14");

    // Re-render toggled states
    rerender(
      <div>
        <Toggle checked={true} onChange={onToggle} label="启用" />
        <IconSwap active={true} first={<span>A</span>} second={<span>B</span>} />
        <SegmentedControl
          label="统计周期"
          value="30"
          onChange={onSegmentChange}
          options={[
            { value: "7", label: "7 天" },
            { value: "14", label: "14 天" },
            { value: "30", label: "30 天" },
          ]}
        />
      </div>,
    );
    expect(screen.getByRole("switch", { name: "启用" }).querySelector("span")?.style.transformOrigin).toBe("right center");
    expect(container.querySelector(".df-icon-swap")).toHaveAttribute("data-swapped", "true");
    expect(screen.getByRole("tablist", { name: "统计周期" }).style.getPropertyValue("--seg-index")).toBe("2");
  });

  it("settles Dialog exit immediately when reduced motion is active", () => {
    document.documentElement.setAttribute("data-motion", "reduced");
    expect(isReducedMotionActive()).toBe(true);
    const onExited = vi.fn();
    const { rerender } = render(
      <Dialog open={true} labelledBy="rm-title" onClose={vi.fn()} onExited={onExited}>
        <h2 id="rm-title">减少动态效果测试</h2>
      </Dialog>,
    );
    rerender(
      <Dialog open={false} labelledBy="rm-title" onClose={vi.fn()} onExited={onExited}>
        <h2 id="rm-title">减少动态效果测试</h2>
      </Dialog>,
    );
    expect(onExited).toHaveBeenCalledTimes(1);
  });
});

describe("Shared format helpers", () => {
  it("rounds minutes cleanly and preserves English category migration mapping", () => {
    expect(formatMinutes(59.6)).toBe("1h");
    expect(formatMinutes(90)).toBe("1h 30m");
    expect(CATEGORIES).toContain("编程");
    expect(categoryVar("Work")).toBe("--cat-work");
    expect(categoryVar("Coding")).toBe("--cat-code");
  });
});

describe("Async state and concurrency regression guards", () => {
  const idleRecording: RecordingControl = {
    state: {
      recordingMode: "local",
      needsSetup: false,
      isRecording: false,
      isPaused: false,
      isIdlePaused: false,
      isPrivacyPaused: false,
    },
    pending: null,
    run: vi.fn(async () => {}),
  };

  it("prevents duplicate deletes in reduced motion and keeps foreground load unstuck without resurrecting deleted historical cards", async () => {
    document.documentElement.setAttribute("data-motion", "reduced");
    const sampleCard = {
      id: 42,
      category: "编程",
      title: "核心重构",
      summary: "测试并发删除",
      startTime: "2026-11-26T09:00:00",
      endTime: "2026-11-26T09:30:00",
      durationMinutes: 30,
      productivityScore: 90,
      appSites: [],
      distractions: [],
    };
    let resolveDelete!: (v: { ok: boolean; undoToken?: string }) => void;
    const deleteSpy = vi.spyOn(api, "deleteCard").mockImplementation(
      () => new Promise((r) => { resolveDelete = r; }),
    );
    let resolveStaleReload!: (v: { cards: typeof sampleCard[] }) => void;
    let targetDayCalls = 0;
    vi.spyOn(api, "getCards").mockImplementation((d) => {
      if (d === "2026-11-26") {
        targetDayCalls++;
        if (targetDayCalls === 1) return Promise.resolve({ cards: [sampleCard] });
        if (targetDayCalls === 2) {
          return new Promise((r) => { resolveStaleReload = r; });
        }
        return Promise.resolve({ cards: [] });
      }
      return Promise.resolve({ cards: [] });
    });

    const { rerender } = render(
      <TimelinePage
        date="2026-11-26"
        onDateChange={vi.fn()}
        onOpenReports={vi.fn()}
        active={true}
        activityFocus={null}
        recordingControl={idleRecording}
      />,
    );

    await screen.findByText("核心重构");
    const deleteBtn = screen.getByRole("button", { name: "删除" });
    fireEvent.click(deleteBtn);
    fireEvent.click(deleteBtn);
    expect(deleteSpy).toHaveBeenCalledTimes(1);
    expect(deleteBtn).toHaveAttribute("aria-busy", "true");
    expect(document.getElementById("activity-42")).not.toHaveAttribute("data-removing");

    // Switch away to another historical day and back while DELETE is still in flight
    rerender(
      <TimelinePage
        date="2026-11-25"
        onDateChange={vi.fn()}
        onOpenReports={vi.fn()}
        active={true}
        activityFocus={null}
        recordingControl={idleRecording}
      />,
    );
    rerender(
      <TimelinePage
        date="2026-11-26"
        onDateChange={vi.fn()}
        onOpenReports={vi.fn()}
        active={true}
        activityFocus={null}
        recordingControl={idleRecording}
      />,
    );

    // DELETE finishes first, then the earlier foreground GET resolves with the pre-delete snapshot
    await act(async () => {
      resolveDelete({ ok: true, undoToken: "tok-42" });
      await Promise.resolve();
      resolveStaleReload({ cards: [sampleCard] });
    });

    await waitFor(() => {
      expect(screen.queryByLabelText("正在加载活动记录")).not.toBeInTheDocument();
      expect(document.querySelector('[aria-busy="true"]')).toBeNull();
    });
    expect(screen.queryByText("核心重构")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "撤销" })).toBeInTheDocument();
    expect(targetDayCalls).toBe(3);
  });

  it("drops stale copy confirmation when switching report dates mid-copy", async () => {
    let resolveClipboard!: () => void;
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: vi.fn(() => new Promise<void>((r) => { resolveClipboard = r; })),
      },
    });
    vi.spyOn(api, "getReportDates").mockResolvedValue({ dates: ["2026-11-28", "2026-11-27"] });
    vi.spyOn(api, "getReport").mockImplementation((day) =>
      Promise.resolve({
        date: day,
        content: `# 日报 ${day}`,
        localSummary: `# 日报 ${day}`,
        supplement: "",
        evidence: [],
        hasActivity: true,
        canSupplement: false,
        isStale: false,
        isLegacy: false,
        hasPrevious: false,
      }),
    );

    render(
      <ReportsPage
        initialDate={{ day: "2026-11-28" }}
        active={true}
        onOpenTimeline={vi.fn()}
        onSetupModel={vi.fn()}
      />,
    );

    const copyBtn = await screen.findByRole("button", { name: "复制日报" });
    fireEvent.click(copyBtn);

    // Switch to another date before clipboard resolves
    const otherDate = screen.getByRole("button", { name: /11\s*月\s*27\s*日/ });
    fireEvent.click(otherDate);
    await screen.findByText("日报 2026-11-27");

    resolveClipboard();
    await Promise.resolve();
    expect(screen.getByRole("button", { name: "复制日报" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "已复制" })).not.toBeInTheDocument();
  });

  it("shows error with retry when switching from empty 7-day stats to failing 30-day stats", async () => {
    vi.spyOn(api, "getStats").mockImplementation((days) => {
      if (days === 7) {
        return Promise.resolve({
          days: 7,
          dailyGoal: 6,
          rangeStart: "2026-11-22",
          rangeEnd: "2026-11-28",
          metrics: {
            totalHours: 0,
            totalMinutes: 0,
            avgScore: 0,
            deepWork: 0,
            deepWorkMinutes: 0,
            activityCount: 0,
            todayHours: 0,
            todayMinutes: 0,
            todayScore: 0,
          },
          changes: { totalHours: 0, avgScore: 0, deepWork: 0, activityCount: 0 },
          categories: [],
          trend: [],
          daily: [],
          hourly: [],
          calendar: [],
          appRanking: [],
        });
      }
      return Promise.reject(new Error("统计服务超时"));
    });

    render(<StatsPage active={true} />);
    await screen.findByText("最近 7 天没有活动记录");

    fireEvent.click(screen.getByRole("tab", { name: "近 30 天" }));
    await screen.findByText("统计数据加载失败");
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  });

  it("defers setupRequest focus until SettingsPage becomes active", async () => {
    let resolveSettings!: (v: Awaited<ReturnType<typeof api.getSettings>>) => void;
    vi.spyOn(api, "getSettings").mockImplementation(
      () => new Promise((r) => { resolveSettings = r; }),
    );
    vi.spyOn(api, "getMonitors").mockResolvedValue({ monitors: [] });
    vi.spyOn(api, "getEmailStatus").mockResolvedValue({ last: null });
    vi.spyOn(api, "getAutostart").mockResolvedValue({ enabled: false, stale: false, available: false });
    vi.spyOn(api, "getStorageInfo").mockResolvedValue({
      chunksDir: "",
      usedBytes: 0,
      usedMb: 0,
      limitGb: 10,
      percent: 0,
      dataDir: "",
      removableCount: 0,
    });
    vi.spyOn(api, "health").mockResolvedValue({ ok: true, version: "1.8.0" });

    const { rerender } = render(<SettingsPage active={false} setupRequest={1} isRecording={false} />);
    resolveSettings({
      recording_mode: "local",
      local_context_mode: "app_only",
      local_ai_refinement: "0",
      api_url: "",
      api_key: "",
      api_key_configured: false,
      api_model: "",
      theme: "light",
      daily_goal: "6",
      idle_pause_enabled: "0",
      idle_pause_timeout_min: "5",
      record_output_idx: "0",
      chunks_max_size_gb: "10",
      custom_chunks_dir: "",
      email_enabled: "0",
      email_ai_enrichment: "0",
      email_sender: "",
      email_auth_code: "",
      email_receiver: "",
      email_send_times: "22:00",
      reduce_motion: "system",
    });

    const apiUrl = await screen.findByLabelText("API 地址");
    const aiSection = document.getElementById("settings-ai")!;
    aiSection.scrollIntoView = vi.fn();
    expect(document.activeElement).not.toBe(apiUrl);

    rerender(<SettingsPage active={true} setupRequest={1} isRecording={false} />);
    await waitFor(() => {
      expect(document.activeElement).toBe(apiUrl);
    });
  });
});

describe("Redesigned unified primitives", () => {
  it("supports keyboard filtering, selection, Escape, and shell inert in CommandPalette", () => {
    const onTimeline = vi.fn();
    const onStats = vi.fn();
    const onClose = vi.fn();
    render(
      <div>
        <div className="df-shell">
          <button type="button">背景入口</button>
        </div>
        <CommandPalette
          open={true}
          onClose={onClose}
          onExited={vi.fn()}
          actions={[
            { id: "a", group: "导航", label: "前往时间轴", icon: "clock", onSelect: onTimeline },
            { id: "b", group: "导航", label: "前往统计", icon: "chart", onSelect: onStats },
          ]}
        />
      </div>,
    );

    const shell = document.querySelector(".df-shell") as HTMLElement;
    expect(shell.hasAttribute("inert")).toBe(true);

    const input = screen.getByRole("combobox", { name: "输入命令或页面名称" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onStats).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.change(input, { target: { value: "时间轴" } });
    expect(screen.getAllByRole("option")).toHaveLength(1);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onTimeline).toHaveBeenCalledTimes(1);
  });

  it("steps and clamps values with presets in NumberStepper", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <NumberStepper
        id="goal-test"
        ariaLabel="每日目标"
        min={1}
        max={24}
        unit="小时"
        presets={[4, 6, 8]}
        value="6"
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "增加" }));
    expect(onChange).toHaveBeenCalledWith("7");

    fireEvent.click(screen.getByRole("button", { name: "减少" }));
    expect(onChange).toHaveBeenCalledWith("5");

    fireEvent.click(screen.getByRole("button", { name: "8小时" }));
    expect(onChange).toHaveBeenCalledWith("8");

    rerender(
      <NumberStepper
        id="goal-test"
        ariaLabel="每日目标"
        min={1}
        max={24}
        unit="小时"
        value="1"
        onChange={onChange}
      />,
    );
    expect(screen.getByRole("button", { name: "减少" })).toBeDisabled();
  });

  it("opens Tooltip on keyboard focus and renders ChartPopover with edge-aware alignment", () => {
    render(
      <div>
        <Tooltip content="前往统计" placement="right">
          <button type="button">图标按钮</button>
        </Tooltip>
        <ChartPopover xPct={10} yPx={24} title="2026-11-28" value="88 分" meta="5.5 小时" color="var(--accent)" />
        <ChartPopover xPct={90} yPx={24} title="2026-11-29" value="92 分" color="var(--accent)" />
      </div>,
    );

    act(() => screen.getByRole("button", { name: "图标按钮" }).focus());
    expect(screen.getByRole("tooltip")).toHaveTextContent("前往统计");

    const popovers = document.querySelectorAll(".df-chart-popover");
    expect(popovers).toHaveLength(2);
    expect(popovers[0]).toHaveAttribute("data-align", "left");
    expect(popovers[1]).toHaveAttribute("data-align", "right");
  });
});
