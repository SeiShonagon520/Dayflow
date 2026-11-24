/*
 * 设置页
 *
 * 按「用户什么时候需要它」分组，不按后端模块分组：
 *   连接 AI → 配置后立即能用
 *   录制     → 影响数据采集
 *   通知     → 邮件日报
 *   存储     → 磁盘占用，删了会丢东西
 *   关于     → 版本与更新
 *
 * 每一组独立保存，不做「全局保存」—— 用户改完一个开关就能走，
 * 不用先滚到底部点保存。
 */

import { useEffect, useRef, useState } from "react";
import { ApiError, Settings, api } from "@/lib/api";
import { Button, Field, Input, Select, Spinner, Toggle } from "@/components/ui";
import { Dialog } from "@/components/Dialog";
import { DataTools, LogTools } from "@/components/DesktopTools";
import { MotionControl } from "@/components/MotionControl";
import { LineIcon, LineIconName } from "@/components/LineIcon";
import { useIsPhone } from "@/lib/useMediaQuery";

const GROUPS = {
  ai: ["api_url", "api_model", "api_key"],
  record: ["record_output_idx", "idle_pause_enabled", "idle_pause_timeout_min", "custom_chunks_dir", "chunks_max_size_gb", "daily_goal"],
  email: ["email_enabled", "email_sender", "email_receiver", "email_auth_code", "email_send_times"],
} as const;

type Group = keyof typeof GROUPS;
type Notice = { kind: "ok" | "err"; text: string };
type Section = {
  id: string;
  icon: LineIconName;
  title: string;
  desc?: string;
  group?: Group;
  body: (s: Settings, set: (key: string, value: string) => void) => React.ReactNode;
};

function validate(group: Group, values: Settings) {
  if (group === "ai") {
    try {
      const url = new URL(values.api_url);
      if (!["http:", "https:"].includes(url.protocol)) throw new Error();
    } catch {
      return { field: "api-url", text: "请输入以 http:// 或 https:// 开头的有效地址" };
    }
    if (!values.api_model.trim()) return { field: "api-model", text: "请输入模型名称" };
  }
  if (group === "record") {
    const numbers = [
      { id: "goal", label: "每日目标", value: values.daily_goal, min: 1, max: 24 },
      { id: "cache-limit", label: "切片容量", value: values.chunks_max_size_gb, min: 1, max: 500 },
      ...(values.idle_pause_enabled === "1"
        ? [{ id: "idle", label: "空闲暂停时长", value: values.idle_pause_timeout_min, min: 1, max: 120 }]
        : []),
    ];
    for (const { id, label, value, min, max } of numbers) {
      const number = Number(value);
      if (!Number.isInteger(number) || number < min || number > max) {
        return { field: id, text: `${label}请输入 ${min} 到 ${max} 之间的整数` };
      }
    }
  }
  if (group === "email" && values.email_enabled === "1") {
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(values.email_sender.trim())) return { field: "mail-from", text: "请输入有效的发件邮箱" };
    if (!values.email_auth_code.trim()) return { field: "mail-auth", text: "请输入发件邮箱的 SMTP 授权码" };
    if (!emailPattern.test(values.email_receiver.trim())) return { field: "mail-to", text: "请输入有效的收件邮箱" };
  }
  return null;
}

export function SettingsPage({ setupRequest, isRecording }: { setupRequest: number; isRecording: boolean }) {
  const [s, setS] = useState<Settings | null>(null);
  const [saved, setSaved] = useState<Settings | null>(null);
  const [notices, setNotices] = useState<Partial<Record<Group, Notice>>>({});
  const [saving, setSaving] = useState<Partial<Record<Group, boolean>>>({});
  const [testing, setTesting] = useState(false);
  const [mailTesting, setMailTesting] = useState(false);
  const [mailStatus, setMailStatus] = useState<Awaited<ReturnType<typeof api.getEmailStatus>>["last"]>(null);
  const [monitors, setMonitors] = useState<Awaited<ReturnType<typeof api.getMonitors>>["monitors"]>([]);
  const [loadError, setLoadError] = useState("");
  const handledSetup = useRef(0);

  const notify = (group: Group, notice?: Notice) => setNotices((current) => ({ ...current, [group]: notice }));

  const load = async () => {
    setLoadError("");
    try {
      const values = await api.getSettings();
      setS(values);
      setSaved(values);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "读取设置失败");
    }
  };

  useEffect(() => {
    void load();
    api.getMonitors().then(result => setMonitors(result.monitors)).catch(() => {});
    api.getEmailStatus().then(result => setMailStatus(result.last)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!s || setupRequest <= handledSetup.current) return;
    handledSetup.current = setupRequest;
    document.getElementById("settings-ai")?.scrollIntoView({ block: "start" });
    document.getElementById(s.api_url ? "api-key" : "api-url")?.focus({ preventScroll: true });
  }, [s, setupRequest]);

  const set = (key: string, value: string) => {
    setS((current) => current ? { ...current, [key]: value } : current);
    const group = (Object.keys(GROUPS) as Group[]).find((item) => (GROUPS[item] as readonly string[]).includes(key));
    if (group) notify(group);
  };

  const check = (group: Group, draft: Settings) => {
    const error = validate(group, draft);
    if (!error) return true;
    notify(group, { kind: "err", text: error.text });
    document.getElementById(error.field)?.focus();
    return false;
  };

  const changed = (group: Group) => GROUPS[group].filter((key) => s?.[key] !== saved?.[key]);

  const save = async (group: Group) => {
    if (!s || saving[group] || !check(group, s)) return;
    const keys = changed(group);
    if (!keys.length) return;
    const patch = Object.fromEntries(keys.map((key) => [key, s[key].trim()]));
    setSaving((current) => ({ ...current, [group]: true }));
    try {
      const result = await api.saveSettings(patch);
      const savedDisplay = Object.fromEntries(Object.entries(patch).map(([key, value]) =>
        key === "api_key" || key === "email_auth_code" ? [key, value ? "********" : ""] : [key, value]));
      const configured = group === "ai" && result.apiKeyConfigured !== undefined
        ? { api_key_configured: result.apiKeyConfigured }
        : "api_key" in patch ? { api_key_configured: !!patch.api_key } : {};
      if (group === "ai" && result.apiKeyConfigured === false) savedDisplay.api_key = "";
      setSaved((current) => current ? { ...current, ...savedDisplay, ...configured } : current);
      setS((current) => {
        if (!current) return current;
        const next: Settings = { ...current, ...configured };
        for (const key of Object.keys(savedDisplay)) if (current[key] === s[key]) next[key] = savedDisplay[key];
        return next;
      });
      notify(group, { kind: "ok", text: "已保存" });
    } catch (error) {
      notify(group, { kind: "err", text: error instanceof Error ? error.message : "保存失败，请重试" });
    } finally {
      setSaving((current) => ({ ...current, [group]: false }));
    }
  };

  const test = async () => {
    if (!s || !check("ai", s)) return;
    setTesting(true);
    notify("ai");
    try {
      const result = await api.testConnection({ api_url: s.api_url, api_model: s.api_model, api_key: s.api_key });
      notify("ai", { kind: result.ok ? "ok" : "err", text: result.ok ? "模型连接成功" : result.message });
    } catch (error) {
      notify("ai", { kind: "err", text: error instanceof Error ? error.message : "测试失败，请重试" });
    } finally {
      setTesting(false);
    }
  };

  const testEmail = async () => {
    if (!s || !check("email", { ...s, email_enabled: "1" })) return;
    setMailTesting(true);
    notify("email");
    try {
      await api.sendTestEmail({ email_sender: s.email_sender, email_receiver: s.email_receiver, email_auth_code: s.email_auth_code });
      notify("email", { kind: "ok", text: "测试邮件已发送到填写的收件邮箱" });
    } catch (error) {
      notify("email", { kind: "err", text: error instanceof Error ? error.message : "邮件发送失败" });
    } finally {
      setMailTesting(false);
    }
  };

  const chooseDirectory = async () => {
    try {
      const path = await api.selectChunksDirectory();
      if (path) set("custom_chunks_dir", path);
    } catch {
      notify("record", { kind: "err", text: "无法打开目录选择，请重新选择" });
    }
  };

  // Hook 必须在所有 early return 之前调用。
  // 之前放在 early return 之后，加载慢的那一帧会少一个 hook，
  // React 直接抛 "Rendered more hooks than during the previous render"
  // —— 整个设置页白掉。错误边界把它兜住了，但页面对用户仍然是坏的。
  const phone = useIsPhone();

  if (loadError) {
    return (
      <div style={{ padding: "var(--space-8)", textAlign: "center" }}>
        <p style={{ color: "var(--danger)", marginBottom: 12 }}>{loadError}</p>
        <Button onClick={load}>重试</Button>
      </div>
    );
  }

  if (!s) {
    return (
      <div className="df-wait" role="status">
        <Spinner size={20} />正在读取设置
      </div>
    );
  }

  const SECTIONS: Section[] = [
    {
      id: "ai",
      icon: "sparkles",
      title: "连接分析模型",
      desc: "选择能识别截图的模型，用于整理活动和生成日报。",
      group: "ai",
      body: (_s, set) => (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <Field label="API 地址" htmlFor="api-url" hint="填写模型服务提供的 OpenAI 兼容地址。">
            <Input
              id="api-url"
              value={s.api_url}
              onChange={(e) => set("api_url", e.target.value)}
              placeholder="https://api.openai.com/v1"
              style={{ width: "100%" }}
            />
          </Field>

          <Field
            label="接口密钥"
            htmlFor="api-key"
            hint={
              s.api_key_configured
                ? "已保存密钥。修改时填写新密钥。"
                : "本机模型通常不需要密钥。使用在线服务时请填写服务提供方的密钥。"
            }
          >
            <Input
              id="api-key"
              type="password"
              value={s.api_key === "********" ? "" : s.api_key}
              onChange={(e) => set("api_key", e.target.value)}
              placeholder={s.api_key_configured ? "已保存，留空不修改" : "sk-..."}
              style={{ width: "100%" }}
            />
          </Field>

          <Field label="模型名称" htmlFor="api-model" hint="填写服务提供方给出的模型名称。">
            <Input
              id="api-model"
              value={s.api_model}
              onChange={(e) => set("api_model", e.target.value)}
              style={{ width: "100%" }}
            />
          </Field>

          <div>
            <Button onClick={test} loading={testing} disabled={!!saving.ai}>
              测试连接
            </Button>
          </div>
        </div>
      ),
    },
    {
      id: "record",
      icon: "record",
      title: "录制",
      desc: "影响后台采集的屏幕活动数据。",
      group: "record",
      body: (_s, set) => (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          {isRecording && <p className="df-context-note">正在录制。停止后可以更改显示器、空闲检测和切片目录。</p>}
          <fieldset className="df-edit-fields" disabled={isRecording}>
          <Field
            label="录制显示器"
            htmlFor="monitor"
          >
            <Select
              id="monitor"
              value={s.record_output_idx}
              onChange={(e) => set("record_output_idx", e.target.value)}
              style={{ width: 220 }}
            >
              {(monitors.length ? monitors : [{ index: 0, width: 0, height: 0 }]).map((screen) => (
                <option key={screen.index} value={screen.index}>
                  显示器 {screen.index + 1}{screen.width ? ` · ${screen.width} × ${screen.height}` : ""}
                </option>
              ))}
              {Number(s.record_output_idx) > 0 && !monitors.some(screen => screen.index === Number(s.record_output_idx)) && (
                <option value={s.record_output_idx}>显示器 {Number(s.record_output_idx) + 1}（当前未检测到）</option>
              )}
              <option value="-1">全部显示器（拼接）</option>
            </Select>
          </Field>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "var(--space-4)",
            }}
          >
            <div>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)" }}>
                空闲时自动暂停
              </div>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", marginTop: 2 }}>
                键盘和鼠标都没动超过设定时长就暂停录制
              </div>
            </div>
            <Toggle
              label="空闲时自动暂停"
              checked={s.idle_pause_enabled === "1"}
              onChange={(v) => set("idle_pause_enabled", v ? "1" : "0")}
            />
          </div>

          {s.idle_pause_enabled === "1" && (
            <Field label="空闲时长（分钟）" htmlFor="idle">
              <Input
                id="idle"
                type="number"
                min={1}
                max={120}
                value={s.idle_pause_timeout_min}
                onChange={(e) => set("idle_pause_timeout_min", e.target.value)}
                style={{ width: 120 }}
              />
            </Field>
          )}

          <Field label="切片目录" htmlFor="chunks-directory" hint="留空使用默认目录。保存后，新切片会写入所选目录。">
            <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
              <Input id="chunks-directory" value={s.custom_chunks_dir} onChange={(event) => set("custom_chunks_dir", event.target.value)} style={{ flex: 1, minWidth: 180 }} />
              <Button onClick={chooseDirectory} disabled={isRecording}>选择目录</Button>
              {s.custom_chunks_dir && <Button onClick={() => set("custom_chunks_dir", "")} disabled={isRecording}>恢复默认</Button>}
            </div>
          </Field>
          </fieldset>
          <Field label="切片容量上限（GB）" htmlFor="cache-limit">
            <Input id="cache-limit" type="number" min={1} max={500} value={s.chunks_max_size_gb}
              onChange={(event) => set("chunks_max_size_gb", event.target.value)} style={{ width: 120 }} />
          </Field>

          <Field label="每日目标（小时）" htmlFor="goal" hint="统计页的进度条以此为基准">
            <Input
              id="goal"
              type="number"
              min={1}
              max={24}
              value={s.daily_goal}
              onChange={(e) => set("daily_goal", e.target.value)}
              style={{ width: 120 }}
            />
          </Field>
        </div>
      ),
    },
    {
      id: "email",
      icon: "mail",
      title: "邮件日报",
      desc: "开启后在设定时间把当天日报发到邮箱。",
      group: "email",
      body: (_s, set) => (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)" }}>
              启用邮件推送
            </span>
            <Toggle
              label="启用邮件推送"
              checked={s.email_enabled === "1"}
              onChange={(v) => set("email_enabled", v ? "1" : "0")}
            />
          </div>

          {s.email_enabled === "1" && <>
              <Field label="发件邮箱" htmlFor="mail-from">
                <Input
                  id="mail-from"
                  value={s.email_sender}
                  onChange={(e) => set("email_sender", e.target.value)}
                  placeholder="123456789@qq.com"
                  style={{ width: "100%" }}
                />
              </Field>
              <Field
                label="授权码"
                htmlFor="mail-auth"
                hint="QQ 邮箱：设置 → 账户 → 开启 SMTP 服务 → 生成授权码"
              >
                <Input
                  id="mail-auth"
                  type="password"
                  placeholder={s.email_auth_code === "********" ? "已保存" : ""}
                  value={s.email_auth_code === "********" ? "" : s.email_auth_code}
                  onChange={(e) => set("email_auth_code", e.target.value)}
                  style={{ width: "100%" }}
                />
              </Field>
              <Field label="收件邮箱" htmlFor="mail-to">
                <Input
                  id="mail-to"
                  value={s.email_receiver}
                  onChange={(e) => set("email_receiver", e.target.value)}
                  style={{ width: "100%" }}
                />
              </Field>
              <Field
                label="发送时间"
                htmlFor="mail-times"
                hint="24 小时制，逗号分隔，例如 12:00,22:00"
              >
                <Input
                  id="mail-times"
                  value={s.email_send_times}
                  onChange={(e) => set("email_send_times", e.target.value)}
                  style={{ width: 220 }}
                />
              </Field>
              <div>
                <Button onClick={testEmail} loading={mailTesting} disabled={!!saving.email}>发送测试邮件</Button>
              </div>
              {mailStatus && (
                <p role="status" style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
                  上次定时发送 {mailStatus.send_time.replace("T", " ").slice(0, 16)}
                  {mailStatus.success ? " · 成功" : " · 失败，请检查邮箱和网络"}
                </p>
              )}
            </>}
        </div>
      ),
    },
    {
      id: "appearance",
      icon: "sun",
      title: "外观",
      desc: "界面动效强度。跟随系统会读取系统的「减少动态效果」设置。",
      body: () => (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <MotionControl />
        </div>
      ),
    },
    {
      id: "system",
      icon: "monitor",
      title: "系统",
      desc: "开机自启与自动更新。",
      body: () => <SystemSection isRecording={isRecording} />,
    },
    {
      id: "storage",
      icon: "database",
      title: "存储",
      desc: "分析完成后会自动清理已处理的录制片段。",
      body: () => <StorageSection isRecording={isRecording} />,
    },
    { id: "backup", icon: "database", title: "数据导入与导出", desc: "导出仪表盘、活动记录或合并备份。", body: () => <DataTools /> },
    { id: "logs", icon: "file", title: "诊断日志", desc: "查看 Dayflow 最近的运行记录。", body: () => <LogTools /> },
    {
      id: "about",
      icon: "info",
      title: "关于",
      desc: "版本与隐私说明。",
      body: () => <AboutSection />,
    },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        className="df-toolbar"
        data-stacked={phone ? "true" : "false"}
      >
        <div className="df-toolbar-row">
          <h2 className="df-page-title">设置</h2>
        </div>
      </div>

      <div
        className="df-content-pad"
        style={{
          flex: 1,
          overflowY: "auto",
          maxWidth: 720,
          width: "100%",
          marginInline: "auto",
        }}
      >
        {SECTIONS.map((section) => {
          const group = section.group;
          const notice = group ? notices[group] : undefined;
          const edited = group ? changed(group).length > 0 : false;
          const advanced = ["appearance", "backup", "logs", "about"].includes(section.id);
          const heading = (
            <span className="df-settings-heading">
              <LineIcon name={section.icon} />
              <span>{section.title}</span>
            </span>
          );
          const content = <>
            {section.desc && <p className="df-settings-description">{section.desc}</p>}
            {section.body(s, set)}
            {group && (edited || notice) && (
              <div className="df-setting-actions">
                {notice && <span className="df-feedback" role={notice.kind === "err" ? "alert" : "status"}
                  data-error={notice.kind === "err" || undefined}>{notice.text}</span>}
                {edited && <>
                  <Button size="sm" variant="ghost" disabled={!!saving[group]} onClick={() => {
                    if (saved) setS((current) => current ? { ...current, ...Object.fromEntries(
                      GROUPS[group].map((key) => [key, saved[key]]),
                    ) } : current);
                    notify(group);
                  }}>撤回更改</Button>
                  <Button size="sm" variant="primary" loading={saving[group]} onClick={() => save(group)}>
                    {group === "ai" ? "保存模型" : group === "record" ? "保存录制设置" : "保存邮件设置"}
                  </Button>
                </>}
              </div>
            )}
          </>;
          if (advanced) return (
            <details key={section.id} className="df-settings-section">
              <summary>{heading}</summary>
              {content}
            </details>
          );
          return <section key={section.id} id={`settings-${section.id}`} className="df-settings-section">
            <h3>{heading}</h3>
            {content}
          </section>;
        })}
      </div>
    </div>
  );
}

// ── 系统（开机自启 + 更新）────────────────────────────────────

function SystemSection({ isRecording }: { isRecording: boolean }) {
  const [autostart, setAutostart] = useState<{
    enabled: boolean;
    stale: boolean;
    available: boolean;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(
    null
  );
  const [checking, setChecking] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [digest, setDigest] = useState("");
  const [update, setUpdate] = useState<{
    hasUpdate: boolean;
    latestVersion: string;
    downloadUrl: string;
    verifiedInstaller: boolean;
    notes: string;
  } | null>(null);

  const load = () => api.getAutostart().then(setAutostart).catch(() => setAutostart(null));
  useEffect(() => {
    load();
  }, []);

  const toggle = async (enable = !autostart?.enabled) => {
    if (!autostart) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.setAutostart(enable);
      setMsg({ kind: "ok", text: r.message || (autostart.enabled ? "已关闭" : "已开启") });
      await load();
    } catch (e) {
      setMsg({
        kind: "err",
        text: e instanceof ApiError ? e.message : "操作失败",
      });
    } finally {
      setBusy(false);
    }
  };

  const check = async () => {
    setChecking(true);
    setMsg(null);
    setDigest("");
    try {
      const r = await api.checkUpdate();
      setUpdate(r);
      if (!r.hasUpdate) setMsg({ kind: "ok", text: "已是最新版本" });
    } catch (e) {
      setMsg({
        kind: "err",
        text: e instanceof ApiError ? e.message : "检查失败",
      });
    } finally {
      setChecking(false);
    }
  };

  const download = async () => {
    setDownloading(true);
    setMsg(null);
    try {
      setDigest((await api.downloadUpdate()).digest);
      setMsg({ kind: "ok", text: "安装包已下载并通过校验" });
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setDownloading(false);
    }
  };

  const install = async () => {
    setInstalling(true);
    setMsg(null);
    try {
      if ((await api.getRecordingState()).isRecording) await api.stopRecording();
      await api.installUpdate(digest);
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setInstalling(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
      {/* 开机自启 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-4)",
        }}
      >
        <div>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: "var(--weight-medium)" }}>
            开机时自动启动
          </div>
          <div
            style={{
              fontSize: "var(--text-xs)",
              color: "var(--text-tertiary)",
              marginTop: 2,
            }}
          >
            {!autostart?.available ? "安装版可设置登录自启" : autostart.enabled
              ? "登录 Windows 后在托盘启动，已配置模型时自动录制" : "关闭后需要手动打开"}
          </div>
        </div>
        <Toggle
          label="开机时自动启动"
          checked={!!autostart?.enabled}
          onChange={(enable) => toggle(enable)}
          disabled={busy || !autostart?.available}
        />
      </div>

      {/* 路径失效：程序被移动过，注册表还指着老位置 */}
      {autostart?.stale && (
        <div
          role="alert"
          style={{
            padding: "var(--space-3) var(--space-4)",
            background: "var(--warning-bg)",
            border: "1px solid var(--warning)",
            borderRadius: "var(--radius-md)",
            fontSize: "var(--text-sm)",
            color: "var(--warning)",
          }}
        >
          自启动指向旧位置。<Button size="sm" onClick={() => toggle(true)} loading={busy}>修复路径</Button>
        </div>
      )}

      {/* 更新 */}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <Button onClick={check} loading={checking} disabled={downloading || installing}>
            检查更新
          </Button>
          {update?.hasUpdate && (
            <span style={{ fontSize: "var(--text-sm)", color: "var(--accent-text)" }}>
              发现新版本 {update.latestVersion}
            </span>
          )}
        </div>
        {update?.hasUpdate && update.notes && (
          <details style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}><summary>发行说明</summary>{update.notes}</details>
        )}
        {update?.hasUpdate && update.verifiedInstaller && !digest && (
          <div><Button onClick={download} loading={downloading}>下载安装包</Button></div>
        )}
        {digest && (
          <div><Button variant="primary" onClick={install} loading={installing}>
            {isRecording ? "保存录制并安装" : "退出并安装"}
          </Button></div>
        )}
        {update?.hasUpdate && update.downloadUrl && !update.verifiedInstaller && (
          <a
            href={update.downloadUrl}
            target="_blank"
            rel="noreferrer"
            style={{ fontSize: "var(--text-sm)" }}
          >
            打开官方下载 {update.latestVersion}
          </a>
        )}
      </div>

      {msg && (
        <span
          style={{
            fontSize: "var(--text-xs)",
            color: msg.kind === "ok" ? "var(--success)" : "var(--danger)",
          }}
          key={msg.text}
          role={msg.kind === "err" ? "alert" : "status"}
          className="df-feedback"
        >
          {msg.kind === "ok" ? "✓ " : "✗ "}
          {msg.text}
        </span>
      )}
    </div>
  );
}

// ── 存储 ────────────────────────────────────────────────────

function StorageSection({ isRecording }: { isRecording: boolean }) {
  const [info, setInfo] = useState<Awaited<ReturnType<typeof api.getStorageInfo>> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [closing, setClosing] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  const load = () => api.getStorageInfo().then((value) => {
    setInfo(value);
    setLoadFailed(false);
  }).catch(() => setLoadFailed(true));
  useEffect(() => { void load(); }, [isRecording]);

  const clear = async () => {
    if (busy || isRecording) return;
    setBusy(true);
    setNotice(null);
    try {
      const result = await api.clearChunks();
      setClosing(true);
      setNotice({ kind: "ok", text: result.removed ? `已清理 ${result.removed} 个临时文件` : "当前没有可清理的临时文件" });
      await load();
    } catch (error) {
      setNotice({ kind: "err", text: error instanceof Error ? error.message : "清理失败，请重试" });
    } finally {
      setBusy(false);
    }
  };

  if (!info) return loadFailed
    ? <Button onClick={load}>重试读取存储</Button>
    : <p role="status">正在读取存储</p>;

  const removable = info.removableCount ?? 0;
  const pct = Math.min(100, info.percent);
  return (
    <div className="df-edit-fields">
      <div>
        <p className="df-settings-description">录制片段占用 {info.usedMb} MB，上限 {info.limitGb} GB</p>
        <div role="progressbar" aria-label="录制片段占用" aria-valuemin={0} aria-valuemax={100}
          aria-valuenow={pct} style={{ height: 8, background: "var(--bg-sunken)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
          <div className="df-fill" style={{ background: pct >= 90 ? "var(--warning)" : "var(--accent)", transform: `scaleX(${pct / 100})` }} />
        </div>
      </div>
      <p className="df-settings-description">{isRecording
        ? "录制结束后可清理临时文件。"
        : removable > 0 ? `有 ${removable} 个临时文件可以清理。` : "待分析的片段会自动保留，当前无需清理。"}
      </p>
      {!isRecording && removable > 0 && <div>
        <Button onClick={() => { setNotice(null); setClosing(false); setConfirming(true); }}>清理临时文件</Button>
      </div>}
      {notice && (!confirming || closing) && (
        <p className="df-feedback" role={notice.kind === "err" ? "alert" : "status"}
          data-error={notice.kind === "err" || undefined}>{notice.text}</p>
      )}
      {confirming && (
        <Dialog open={!closing} labelledBy="storage-clean-title"
          onClose={() => { if (!busy) setClosing(true); }} onExited={() => setConfirming(false)}>
          <h3 id="storage-clean-title">清理临时文件？</h3>
          <p>清理后，这些文件无法找回。待分析的片段、活动记录和日报会保留。</p>
          {!closing && notice?.kind === "err" && <p role="alert" data-error="true">{notice.text}</p>}
          <div className="df-setting-actions">
            <Button disabled={busy} onClick={() => setClosing(true)}>取消</Button>
            <Button variant="danger" disabled={isRecording} loading={busy} onClick={clear}>确认清理</Button>
          </div>
        </Dialog>
      )}
    </div>
  );
}

// ── 关于与更新 ────────────────────────────────────────────────

function AboutSection() {
  const [v, setV] = useState("");
  const [health, setHealth] = useState<"up" | "down" | null>(null);

  useEffect(() => {
    api
      .health()
      .then((r) => {
        setV(r.version);
        setHealth("up");
      })
      .catch(() => setHealth("down"));
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
          Dayflow
        </span>
        <span
          className="u-tabular"
          style={{ fontSize: "var(--text-sm)", color: "var(--text-tertiary)" }}
        >
          {v ? `v${v}` : "版本未知"}
        </span>
        <span
          style={{
            fontSize: "var(--text-xs)",
            color: health === "up" ? "var(--success)" : "var(--danger)",
          }}
        >
          {health === "up" ? "后台服务正常" : health === "down" ? "后台服务未连接" : ""}
        </span>
      </div>

      <p style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", lineHeight: "var(--leading-normal)" }}>
        录屏切片只保存在本机，仅提取关键帧发送给配置的视觉模型进行分析。
        分析结果存放在本地 SQLite 数据库。
      </p>
    </div>
  );
}
