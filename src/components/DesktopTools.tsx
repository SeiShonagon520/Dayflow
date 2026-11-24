import { useState } from "react";
import { api, saveTextFile } from "@/lib/api";
import { fullDate, shiftDate, todayStr } from "@/lib/format";
import { Button, Field, Input, Select, Toggle } from "@/components/ui";

export function DataTools() {
  const today = todayStr();
  const [period, setPeriod] = useState("today");
  const [customStart, setCustomStart] = useState(todayStr);
  const [customEnd, setCustomEnd] = useState(todayStr);
  const start = period === "custom" ? customStart : period === "week" ? shiftDate(today, -6)
    : period === "yesterday" ? shiftDate(today, -1) : today;
  const end = period === "custom" ? customEnd : period === "yesterday" ? start : today;
  const validRange = !!start && !!end && start <= end && end <= today;
  const filenameDate = start === end ? start : `${start}_${end}`;
  const [file, setFile] = useState<File | null>(null);
  const [restoreSettings, setRestoreSettings] = useState(false);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);

  async function run(action: string, operation: () => Promise<string>) {
    setBusy(action);
    setMessage(null);
    try {
      setMessage({ text: await operation(), error: false });
    } catch (error) {
      setMessage({ text: String(error instanceof Error ? error.message : error), error: true });
    } finally {
      setBusy("");
    }
  }

  async function save(name: string, content: string, extension: string) {
    return await saveTextFile(name, content, extension) ? "已保存" : "已取消保存";
  }

  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      <Field label="导出范围" htmlFor="export-range">
        <Select id="export-range" value={period} onChange={(event) => setPeriod(event.target.value)}>
          <option value="today">今天</option>
          <option value="yesterday">昨天</option>
          <option value="week">最近 7 天</option>
          <option value="custom">自选日期</option>
        </Select>
      </Field>
      {period === "custom" && <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <Field label="起始日期" htmlFor="dashboard-start">
          <Input id="dashboard-start" type="date" value={customStart} max={customEnd || today} onChange={(event) => setCustomStart(event.target.value)} />
        </Field>
        <Field label="结束日期" htmlFor="dashboard-end">
          <Input id="dashboard-end" type="date" value={customEnd} min={customStart} max={today} onChange={(event) => setCustomEnd(event.target.value)} />
        </Field>
      </div>}
      {validRange && <p className="df-settings-description">
        {start === end ? fullDate(start) : `${fullDate(start)} 至 ${fullDate(end)}`}
      </p>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
        <Button loading={busy === "html"} disabled={!!busy && busy !== "html" || !validRange}
          onClick={() => run("html", async () => {
            const report = await api.getDashboard(start, end);
            return save(`Dayflow_${filenameDate}.html`, report.content, "html");
          })}>导出 HTML 仪表盘</Button>
        <Button loading={busy === "csv"} disabled={!!busy && busy !== "csv" || !validRange}
          onClick={() => run("csv", async () => save(`Dayflow_${filenameDate}.csv`, "\uFEFF" + await api.getCsv(start, end), "csv"))}>
          导出 CSV
        </Button>
      </div>
      <details className="df-details">
        <summary>完整备份</summary>
        <div className="df-edit-fields">
        <div><Button loading={busy === "backup"} disabled={!!busy && busy !== "backup"}
          onClick={() => run("backup", async () => save(`Dayflow_${todayStr()}.json`, JSON.stringify(await api.getBackup(), null, 2), "json"))}>
          导出 JSON 备份
        </Button></div>
      <Field label="选择要合并的 JSON 备份" htmlFor="backup-file"
        hint="支持旧版备份，重复活动会跳过。">
        <Input id="backup-file" type="file" accept=".json,application/json" disabled={!!busy}
          onChange={(event) => { setFile(event.target.files?.[0] ?? null); event.target.value = ""; }} />
      </Field>
      {file && <div style={{ overflowWrap: "anywhere" }}>{file.name}</div>}
      {file && <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
        <Toggle label="随备份恢复录制与每日目标设置" checked={restoreSettings} onChange={setRestoreSettings} disabled={!!busy} />
        <span>随备份恢复录制与每日目标设置</span>
      </div>}
      {file && <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <Button variant="ghost" disabled={!!busy} onClick={() => { setFile(null); setRestoreSettings(false); }}>取消选择</Button>
        <Button loading={busy === "import"} disabled={!file || !!busy && busy !== "import"} onClick={() => {
          if (!file) return;
          run("import", async () => {
            if (file.size > 25 * 1024 * 1024) throw new Error("请选择 25 MB 以内的备份");
            const result = await api.importBackup(await file.text(), restoreSettings);
            setFile(null);
            setRestoreSettings(false);
            return `已导入 ${result.imported} 条活动，跳过 ${result.skipped} 条重复记录`;
          });
        }}>合并备份</Button>
      </div>}
        </div>
      </details>
      {message && <span className="df-feedback" role={message.error ? "alert" : "status"}>{message.text}</span>}
    </div>
  );
}

export function LogTools() {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(openDirectory: boolean) {
    setError("");
    setBusy(true);
    try {
      if (openDirectory) await api.openLogDirectory();
      else setContent((await api.getLogs()).content);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
        <Button loading={busy} onClick={() => run(false)}>{content === null ? "查看日志" : "刷新日志"}</Button>
        <Button disabled={busy} onClick={() => run(true)}>打开日志目录</Button>
      </div>
      {error && <span role="alert">{error}</span>}
      {content !== null && (
        <pre tabIndex={0} style={{ margin: 0, maxHeight: 260, overflow: "auto", whiteSpace: "pre-wrap",
          overflowWrap: "anywhere", fontSize: "var(--text-xs)" }}>
          {content || "暂无日志"}
        </pre>
      )}
    </div>
  );
}
