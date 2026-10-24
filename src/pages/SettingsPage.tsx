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

import { useEffect, useState } from "react";
import { ApiError, Settings, api } from "@/lib/api";
import { Button, Field, Input, Select, Spinner, Toggle } from "@/components/ui";
import { MotionControl } from "@/components/MotionControl";
import { LineIcon, LineIconName } from "@/components/LineIcon";
import { useIsPhone } from "@/lib/useMediaQuery";

/* 校验失败时把焦点送到对应字段。
   顺序和校验器的检查顺序一致 —— 焦点落在第一个问题上。
   id 必须是真实存在的：字段 id 对不上，焦点就落空，
   校验等于白做。 */
const FIELDS = [
  { id: "api-url", label: "API 地址" },
  { id: "api-model", label: "模型名称" },
  { id: "goal", label: "每日目标" },
  { id: "idle", label: "空闲暂停时长" },
];

type Section = {
  id: string;
  icon: LineIconName;
  title: string;
  desc: string;
  body: (s: Settings, set: (k: string, v: string) => void) => React.ReactNode;
  /** 这组是否有「立刻生效」的动作（保存/测试），决定要不要显示保存条 */
  needsSave?: boolean;
};

export function SettingsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = async () => {
    try {
      setS(await api.getSettings());
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "加载失败");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const set = (k: string, v: string) => {
    setS((prev) => (prev ? { ...prev, [k]: v } : prev));
    setDirty(true);
    setMsg(null);
  };

  /* 保存前的校验。
     之前把 API 地址清空再保存会静默成功 —— 后端接受了空值，
     用户要到下次分析失败才发现。提交时校验，不是输入时校验：
     边打字边报错是惩罚用户。 */
  const validate = (v: Settings): string[] => {
    const errs: string[] = [];
    if (!v) return errs;
    if (!v.api_url?.trim()) {
      errs.push("API 地址不能为空");
    } else if (!/^https?:\/\//i.test(v.api_url.trim())) {
      errs.push("API 地址要以 http:// 或 https:// 开头");
    }
    if (!v.api_model?.trim()) {
      errs.push("模型名称不能为空");
    }
    const goal = Number(v.daily_goal);
    if (!Number.isFinite(goal) || goal < 1 || goal > 24) {
      errs.push("每日目标要在 1 到 24 小时之间");
    }
    const idle = Number(v.idle_pause_timeout_min);
    if (!Number.isFinite(idle) || idle < 1 || idle > 120) {
      errs.push("空闲暂停时长要在 1 到 120 分钟之间");
    }
    return errs;
  };

  const save = async () => {
    if (!s) return;
    /* 按钮常可点（见下）。没改动时不要白跑一次网络请求，
       也不要说「失败」—— 用户确实没做错什么。 */
    if (!dirty) {
      setMsg({ kind: "ok", text: "没有需要保存的改动" });
      return;
    }
    const errs = validate(s);
    if (errs.length > 0) {
      setMsg({ kind: "err", text: errs[0] });
      // 焦点落到第一个出问题的字段：这既是修复路径，也是播报
      const first = FIELDS.find((f) =>
        errs.some((e) => e.startsWith(f.label)));
      if (first) document.getElementById(first.id)?.focus();
      return;
    }
    setSaving(true);
    try {
      await api.saveSettings({
        api_url: s.api_url,
        api_key: s.api_key === "********" ? undefined : s.api_key,
        api_model: s.api_model,
        /* theme 不在这里存。这一页没有任何主题控件，之前是把后端
           的值读出来再原样存回去 —— 用户在这期间用侧栏切了主题，
           一次保存就把他的选择悄悄改回去了。谁都不管的字段就别回传。 */
        daily_goal: s.daily_goal,
        idle_pause_enabled: s.idle_pause_enabled,
        idle_pause_timeout_min: s.idle_pause_timeout_min,
        record_output_idx: s.record_output_idx,
        chunks_max_size_gb: s.chunks_max_size_gb,
        email_enabled: s.email_enabled,
        email_sender: s.email_sender,
        email_auth_code: s.email_auth_code,
        email_receiver: s.email_receiver,
        email_send_times: s.email_send_times,
      } as Record<string, string>);
      setDirty(false);
      setMsg({ kind: "ok", text: "已保存" });
      await load();
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof ApiError ? e.message : "保存失败" });
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setMsg(null);
    try {
      /* 先保存再测，否则测的是旧配置。
         save() 在校验失败时会提前 return —— 这时不能继续测，
         否则用户看到「连接失败」，实际是表单没填对。 */
      if (dirty && s) {
        const errs = validate(s);
        if (errs.length > 0) {
          setMsg({ kind: "err", text: errs[0] });
          const first = FIELDS.find((f) =>
            errs.some((e) => e.startsWith(f.label)));
          if (first) document.getElementById(first.id)?.focus();
          return;
        }
        await save();
      }
      const r = await api.testConnection();
      setMsg({
        kind: r.ok ? "ok" : "err",
        text: r.ok ? `连接成功：${r.message}` : r.message,
      });
    } catch (e) {
      setMsg({ kind: "err", text: e instanceof ApiError ? e.message : "测试失败" });
    } finally {
      setTesting(false);
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
      <div style={{ display: "flex", justifyContent: "center", padding: 80 }}>
        <Spinner size={20} />
      </div>
    );
  }

  const SECTIONS: Section[] = [
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
      id: "ai",
      icon: "sparkles",
      title: "连接 AI",
      desc: "用于分析屏幕活动和生成日报。需要支持视觉输入的模型。",
      needsSave: true,
      body: (_s, set) => (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <Field label="API 地址" htmlFor="api-url" hint="任何 OpenAI 兼容接口都可以">
            <Input
              id="api-url"
              value={s.api_url}
              onChange={(e) => set("api_url", e.target.value)}
              placeholder="https://api.openai.com/v1"
              style={{ width: "100%" }}
            />
          </Field>

          <Field
            label="API Key"
            htmlFor="api-key"
            hint={
              s.api_key_configured
                ? "已配置。留空则保持不变。"
                : "尚未配置，不填写无法开始分析。"
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

          <Field label="模型名称" htmlFor="api-model" hint="需支持视觉输入，例如 gpt-4o / qwen-vl-plus">
            <Input
              id="api-model"
              value={s.api_model}
              onChange={(e) => set("api_model", e.target.value)}
              style={{ width: "100%" }}
            />
          </Field>

          <div>
            <Button onClick={test} loading={testing}>
              {testing ? "测试中" : "保存并测试连接"}
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
      needsSave: true,
      body: (_s, set) => (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
          <Field
            label="录制显示器"
            htmlFor="monitor"
            hint="0 是主显示器；多屏可选其他编号"
          >
            <Select
              id="monitor"
              value={s.record_output_idx}
              onChange={(e) => set("record_output_idx", e.target.value)}
              style={{ width: 220 }}
            >
              <option value="0">显示器 0（主）</option>
              <option value="1">显示器 1</option>
              <option value="2">显示器 2</option>
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
      needsSave: true,
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

          {s.email_enabled === "1" && (
            <>
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
                  value={s.email_auth_code}
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
            </>
          )}
        </div>
      ),
    },
    {
      id: "system",
      icon: "monitor",
      title: "系统",
      desc: "开机自启与自动更新。",
      body: () => <SystemSection />,
    },
    {
      id: "storage",
      icon: "database",
      title: "存储",
      desc: "临时视频切片占用情况。分析完成后切片会自动清理。",
      body: () => <StorageSection />,
    },
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
          <div className="df-toolbar-spacer" />
        {msg && (
          <span
            role="status"
            /* 错误用 assertive：它是「你没保存成功」，
               不播报用户会以为存上了。 */
            aria-live={msg.kind === "err" ? "assertive" : "polite"}
            style={{
              fontSize: "var(--text-xs)",
              color: msg.kind === "ok" ? "var(--success)" : "var(--danger)",
              maxWidth: 380,
              /* 错误可能很长（「API 地址要以 http:// 或 https:// 开头」）。
                 省略号会把修复方法藏起来 —— 错误要完整可见。 */
              whiteSpace: msg.kind === "err" ? "normal" : "nowrap",
              overflow: msg.kind === "err" ? "visible" : "hidden",
              textOverflow: msg.kind === "err" ? "clip" : "ellipsis",
              textAlign: "right",
            }}
            title={msg.text}
          >
            {msg.kind === "ok" ? "✓ " : "✗ "}
            {msg.text}
          </span>
        )}
        <Button
          variant="primary"
          size="sm"
          onClick={save}
          /* 不用 disabled={!dirty}。规范说：submit 不能 disabled
             到表单有效 —— 一个灰着的按钮把「要改什么」藏起来了。
             改成可点：没改动时点了会走校验，校验通过就再报一次
             「没有要保存的改动」。 */
          loading={saving}
        >
          {saving ? "保存中" : "保存"}
        </Button>
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
        {SECTIONS.map((sec) => (
          <section
            key={sec.id}
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-lg)",
              padding: "var(--space-5)",
              marginBottom: "var(--space-4)",
            }}
          >
            <div style={{ display: "flex", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
              <span aria-hidden style={{ color: "var(--text-tertiary)", width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 }}>
                <LineIcon name={sec.icon} />
              </span>
              <div>
                <h3 style={{ fontSize: "var(--text-md)" }}>{sec.title}</h3>
                <p
                  style={{
                    fontSize: "var(--text-xs)",
                    color: "var(--text-tertiary)",
                    marginTop: 2,
                  }}
                >
                  {sec.desc}
                </p>
              </div>
            </div>
            {sec.body(s, set)}
          </section>
        ))}

        <p
          style={{
            fontSize: "var(--text-xs)",
            color: "var(--text-placeholder)",
            textAlign: "center",
            padding: "var(--space-4) 0",
          }}
        >
          Dayflow 数据保存在本机，不上传完整录屏
        </p>
      </div>
    </div>
  );
}

// ── 系统（开机自启 + 更新）────────────────────────────────────

function SystemSection() {
  const [autostart, setAutostart] = useState<{
    enabled: boolean;
    stale: boolean;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(
    null
  );
  const [checking, setChecking] = useState(false);
  const [update, setUpdate] = useState<{
    hasUpdate: boolean;
    latestVersion: string;
    downloadUrl: string;
  } | null>(null);

  const load = () => api.getAutostart().then(setAutostart).catch(() => setAutostart(null));
  useEffect(() => {
    load();
  }, []);

  const toggle = async () => {
    if (!autostart) return;
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.setAutostart(!autostart.enabled);
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

  if (!autostart) {
    return (
      <p style={{ fontSize: "var(--text-sm)", color: "var(--text-tertiary)" }}>读取中…</p>
    );
  }

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
            {autostart.enabled ? "已开启，系统启动时会自动运行" : "关闭后需要手动打开"}
          </div>
        </div>
        <Toggle
          label="开机时自动启动"
          checked={autostart.enabled}
          onChange={toggle}
          disabled={busy}
        />
      </div>

      {/* 路径失效：程序被移动过，注册表还指着老位置 */}
      {autostart.stale && (
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
          程序路径已变化，自启动指向旧位置。关闭再开启即可修复。
        </div>
      )}

      {/* 更新 */}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <Button onClick={check} loading={checking}>
            检查更新
          </Button>
          {update?.hasUpdate && (
            <span style={{ fontSize: "var(--text-sm)", color: "var(--accent-text)" }}>
              发现新版本 {update.latestVersion}
            </span>
          )}
        </div>
        {update?.hasUpdate && update.downloadUrl && (
          <a
            href={update.downloadUrl}
            target="_blank"
            rel="noreferrer"
            style={{ fontSize: "var(--text-sm)" }}
          >
            下载 {update.latestVersion} →
          </a>
        )}
      </div>

      {msg && (
        <span
          role="status"
          style={{
            fontSize: "var(--text-xs)",
            color: msg.kind === "ok" ? "var(--success)" : "var(--danger)",
          }}
          // 成功给一次短促的提亮，失败抖一下。
          // 两者都只做一次，不循环 —— 常规操作不配礼花。
          className={msg.kind === "ok" ? "df-success-flash" : "df-shake"}
        >
          {msg.kind === "ok" ? "✓ " : "✗ "}
          {msg.text}
        </span>
      )}
    </div>
  );
}

// ── 存储 ────────────────────────────────────────────────────

function StorageSection() {
  const [info, setInfo] = useState<Awaited<ReturnType<typeof api.getStorageInfo>> | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = () => api.getStorageInfo().then(setInfo).catch(() => setInfo(null));
  useEffect(() => {
    load();
  }, []);

  if (!info) return <p style={{ fontSize: "var(--text-sm)", color: "var(--text-tertiary)" }}>读取中…</p>;

  const pct = Math.min(100, info.percent);
  const over = info.percent > 90;

  const clear = async () => {
    setBusy(true);
    try {
      const r = await api.clearChunks();
      setMsg(`已清理 ${r.removed} 个文件`);
      await load();
    } catch {
      setMsg("清理失败，请查看日志");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      <div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: "var(--text-sm)",
            marginBottom: 6,
          }}
        >
          <span>切片占用</span>
          <span className="u-tabular" style={{ color: "var(--text-secondary)" }}>
            {info.usedMb} MB / {info.limitGb} GB
          </span>
        </div>
        <div
          style={{
            height: 8,
            background: "var(--bg-sunken)",
            borderRadius: "var(--radius-full)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${pct}%`,
              height: "100%",
              // 接近上限变橙：状态用颜色 + 下面的文案双重表达
              background: over ? "var(--warning)" : "var(--accent)",
              transition: "width var(--dur-space) var(--ease-out)",
            }}
          />
        </div>
        <p
          style={{
            fontSize: "var(--text-xs)",
            color: over ? "var(--warning)" : "var(--text-tertiary)",
            marginTop: 6,
          }}
        >
          {over
            ? `已用 ${pct}%，接近上限。清理后录制不受影响。`
            : `已用 ${pct}%`}
        </p>
      </div>

      <div>
        <p style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", marginBottom: 2 }}>
          切片目录
        </p>
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-xs)",
            color: "var(--text-secondary)",
            wordBreak: "break-all",
          }}
        >
          {info.chunksDir}
        </p>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
        <Button onClick={clear} loading={busy} disabled={info.usedMb === 0}>
          清理临时切片
        </Button>
        {msg && (
          <span style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)" }}>{msg}</span>
        )}
      </div>
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
