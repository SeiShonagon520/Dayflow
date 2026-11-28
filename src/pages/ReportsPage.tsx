/*
 * 日报页
 *
 * 左侧日期列表 + 右侧内容。旧界面这里是「左列表 + 右浏览器 + 底部
 * 两个灰按钮」，空的时候灰按钮不解释为什么。现在空状态直接给引导，
 * 按钮的 tooltip 说明它为什么被禁用。
 *
 * Markdown 渲染用一个极简实现：只处理日报里实际会用到的语法
 * （标题、列表、表格、引用、代码、粗体）。引第三方库要额外下载体积，
 * 而日报的语法空间是可预测的。
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { api, DailyReport, saveTextFile } from "@/lib/api";
import { fullDate, prettyDate, todayStr, weekdayOf } from "@/lib/format";
import { Badge, Button, EmptyState, IconSwap, SectionTitle, Spinner } from "@/components/ui";
import { LineIcon } from "@/components/LineIcon";
import { useLatest } from "@/lib/useLatest";
import { LoadingHandoff } from "@/components/LoadingHandoff";
import { useIsPhone } from "@/lib/useMediaQuery";
import { TimelineSignature } from "@/components/TimelineSignature";

export function ReportsPage({
  initialDate, active, onOpenTimeline, onSetupModel,
}: {
  initialDate: { day: string } | null;
  active: boolean;
  onOpenTimeline: (day: string, id?: number) => void;
  onSetupModel: () => void;
}) {
  const today = todayStr();
  const [dates, setDates] = useState<string[]>([]);
  const [selected, setSelected] = useState(() => initialDate?.day ?? today);
  const [report, setReport] = useState<DailyReport | null>(null);
  const [readError, setReadError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [dateError, setDateError] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null);
  const [generating, setGenerating] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [copied, setCopied] = useState(false);
  const selection = useLatest(selected);
  const readRequest = useRef(0);
  const copyRequest = useRef(0);
  const generationLock = useRef(false);
  const copyTimer = useRef<number | null>(null);
  const reportPane = useRef<HTMLDivElement>(null);
  const phone = useIsPhone();

  useEffect(() => () => {
    ++copyRequest.current;
    if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
  }, []);

  const loadDates = async () => {
    try {
      setDates((await api.getReportDates()).dates ?? []);
      setDateError(false);
    } catch {
      setDateError(true);
    }
  };

  const loadReport = async (day: string) => {
    const id = ++readRequest.current;
    setReadError("");
    try {
      const result = await api.getReport(day);
      if (id === readRequest.current) setReport({ ...result, date: day });
    } catch (error) {
      if (id === readRequest.current) {
        setReadError(error instanceof Error ? error.message : "读取日报失败");
      }
    }
  };

  useEffect(() => { if (initialDate) setSelected(initialDate.day); }, [initialDate]);
  useEffect(() => { if (active) void loadDates(); }, [active]);
  useEffect(() => {
    if (!active) return;
    ++copyRequest.current;
    setNotice(null);
    setCopied(false);
    if (copyTimer.current !== null) {
      window.clearTimeout(copyTimer.current);
      copyTimer.current = null;
    }
    if (reportPane.current) reportPane.current.scrollTop = 0;
    void loadReport(selected);
    return () => { ++readRequest.current; };
  }, [active, selected]);

  const current = report?.date === selected ? report : null;
  const content = current?.content ?? "";
  const evidence = current?.evidence ?? [];
  const openEvidence = (id: number) => onOpenTimeline(selected, id);
  const evidenceAction = (id: number) => evidence.some((item) => item.id === id) ? () => openEvidence(id) : undefined;
  const reportDays = Array.from(new Set([today, selected, ...dates])).sort().reverse();

  useEffect(() => {
    if (!active || selected !== today || !current || readError || generating) return;
    const timer = window.setInterval(() => { if (!document.hidden) void loadReport(selected); }, 8000);
    return () => window.clearInterval(timer);
  }, [active, selected, today, !!current, readError, generating]);

  const retry = async () => {
    setRetrying(true);
    await loadReport(selected);
    setRetrying(false);
  };

  const showError = (error: unknown, fallback: string) => {
    setNotice({ text: error instanceof Error ? error.message : fallback, error: true });
  };

  const generate = async () => {
    if (generationLock.current || !current?.canSupplement) return;
    generationLock.current = true;
    const day = selected;
    setGenerating(day);
    setNotice(null);
    try {
      const next = await api.generateReport(day);
      if (selection.current === day) {
        ++readRequest.current;
        setReadError("");
        setReport(next);
        setNotice({ text: next.isStale ? "补充已保存，活动在生成期间有更新。" : "AI 补充已保存" });
      }
      void loadDates();
    } catch (error) {
      if (selection.current === day) showError(error, "AI 补充失败，请重试");
    } finally {
      generationLock.current = false;
      setGenerating(null);
    }
  };

  const restore = async () => {
    if (restoring || generating) return;
    const day = selected;
    setRestoring(true);
    try {
      const result = await api.restoreReport(day);
      if (selection.current === day) {
        ++readRequest.current;
        setReport(result);
        setNotice({ text: "已切回上一版" });
      }
    } catch (error) {
      if (selection.current === day) showError(error, "恢复上一版失败，请重试");
    } finally {
      setRestoring(false);
    }
  };

  const copy = async () => {
    const day = selected;
    const op = ++copyRequest.current;
    try {
      await navigator.clipboard.writeText(content);
      if (op !== copyRequest.current || selection.current !== day) return;
      setCopied(true);
      if (copyTimer.current !== null) window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => {
        copyTimer.current = null;
        if (op === copyRequest.current && selection.current === day) setCopied(false);
      }, 1600);
    } catch {
      if (op !== copyRequest.current || selection.current !== day) return;
      setCopied(false);
      setNotice({ text: "复制失败，可以保存 Markdown 文件。", error: true });
    }
  };

  const exportMd = async () => {
    setExporting(true);
    try {
      if (await saveTextFile(`日报_${selected}.md`, content, "md")) {
        setNotice({ text: "日报已保存" });
      }
    } catch (error) {
      showError(error, "保存日报失败，请重试");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="df-toolbar" data-stacked={phone ? "true" : "false"}>
        <div className="df-toolbar-row">
          <TimelineSignature />
          <h2 className="df-page-title">日报</h2>
          <div className="df-toolbar-spacer" />
          {content && <>
            <Button size="sm" onClick={copy}>
              <IconSwap
                active={copied}
                size={14}
                first={<LineIcon name="copy" size={14} />}
                second={<LineIcon name="check" size={14} />}
              />
              <span className="df-copy-label">{copied ? "已复制" : "复制日报"}</span>
            </Button>
            <span className="u-sr-only" role="status">{copied ? "已复制日报" : ""}</span>
            <Button size="sm" onClick={exportMd} loading={exporting}>保存文件</Button>
          </>}
        </div>
      </div>

      <div className="df-split" data-stacked={phone ? "true" : "false"}
        style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div className="df-split-aside"
          style={{ flexShrink: 0, borderRight: phone ? "none" : "1px solid var(--border-subtle)", overflowY: phone ? "hidden" : "auto", padding: phone ? undefined : "var(--space-3)" }}>
          {!phone && <SectionTitle>日期</SectionTitle>}
          {reportDays.map((day) => (
            <button key={day} onClick={() => setSelected(day)}
              aria-current={day === selected ? "true" : undefined}
              className="df-report-date">
              <span className="df-selection-mark" aria-hidden>●</span>
              {day === today ? "今天" : prettyDate(day)}
              <span className="df-report-weekday">{weekdayOf(day)}</span>
            </button>
          ))}
          {dateError && <Button size="sm" variant="ghost" onClick={loadDates}>重试读取日期</Button>}
        </div>

        <div ref={reportPane} style={{ flex: 1, overflowY: "auto", minWidth: 0 }}>
          {generating && generating !== selected && (
            <p className="df-context-note df-feedback" role="status">正在补充 {prettyDate(generating)} 的日报，可以先阅读其他日期。</p>
          )}
          {notice && (
            <p className="df-context-note df-feedback" role={notice.error ? "alert" : "status"}
              data-error={notice.error || undefined}>{notice.text}</p>
          )}
          {readError && content && <div className="df-inline-notice df-feedback" role="alert">
            <span>刷新失败，当前仍显示已打开的日报。</span>
            <Button size="sm" onClick={retry} loading={retrying}>重试读取</Button>
          </div>}
          <LoadingHandoff retainOnReload loading={(!current && !readError) || (retrying && !content)}
            skeleton={<div className="df-wait"><Spinner />正在读取日报</div>}>
            {readError && !content ? (
              <EmptyState icon={<LineIcon name="alert" size={28} />} title="日报读取失败" description={readError}
                action={<Button onClick={retry}>重试读取</Button>} />
            ) : content ? (
              <div className="df-report-stage">
                <article className="df-report-sheet">
                  <header className="df-report-doc-head">
                    <p className="df-report-weekday">{fullDate(selected)}</p>
                    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexWrap: "wrap" }}>
                      <Badge tone="neutral">本机总结</Badge>
                      {current?.supplement && (
                        <Badge tone={current.isStale ? "warning" : "accent"}>
                          {current.isLegacy ? "历史日报" : current.isStale ? "AI 补充待刷新" : "已含 AI 补充"}
                        </Badge>
                      )}
                    </div>
                  </header>
                  {current?.localSummary && <Markdown source={current.localSummary} onEvidence={evidenceAction} />}
                  {evidence.length > 0 && (
                    <section className="df-evidence-list" aria-label="相关活动">
                      <SectionTitle>相关活动</SectionTitle>
                      {evidence.map((item) => (
                        <Button key={item.id} variant="secondary" size="sm" onClick={() => openEvidence(item.id)}>
                          {item.start}–{item.end} · {item.title || "未命名活动"}
                        </Button>
                      ))}
                    </section>
                  )}
                  {current?.supplement && (
                    <section className="df-report-ai-surface" aria-label={current.isLegacy ? "历史日报" : "AI 补充"}>
                      <div className="df-report-ai-head">
                        <LineIcon name="sparkles" size={15} />
                        <h3 style={{ fontSize: "var(--text-md)" }}>{current.isLegacy ? "历史日报" : "AI 补充"}</h3>
                        {current.isStale && <Badge tone="warning">活动已更新</Badge>}
                      </div>
                      {current.isStale && <p className="df-settings-description" style={{ marginBottom: "var(--space-3)" }}>活动有更新，本机总结已刷新。可重新补充。</p>}
                      <Markdown source={current.supplement} onEvidence={evidenceAction} />
                    </section>
                  )}
                  {current && (current.canSupplement || current.hasPrevious || (current.hasActivity && !current.supplement)) && (
                    <div className="df-details">
                      {current.canSupplement && (!current.supplement || current.isStale) && (
                        <>
                          <p>会将本机统计和上述活动标题、类别及时段发送给配置的模型。</p>
                          <Button size="sm" onClick={generate} loading={generating === selected}
                            disabled={restoring || !!generating && generating !== selected}>
                            {current.supplement ? "更新 AI 补充" : "用 AI 补充"}
                          </Button>
                        </>
                      )}
                      {!current.canSupplement && current.hasActivity && !current.supplement && (
                        <Button size="sm" variant="ghost" onClick={onSetupModel}>连接模型以补充日报</Button>
                      )}
                      {current.hasPrevious && <Button size="sm" variant="ghost" onClick={restore}
                        loading={restoring} disabled={!!generating}>恢复上一版</Button>}
                    </div>
                  )}
                </article>
              </div>
            ) : (
              <EmptyState icon={<LineIcon name="clipboard" size={28} />} title={selected === today ? "今天还没有可汇总的活动" : "这一天没有可汇总的活动"}
                description={selected === today ? "开始本机计时后，这里会自动显示当天的总结。" : "可以查看这一天的时间轴，或选择其他日期。"}
                action={<Button onClick={() => onOpenTimeline(selected)}>查看时间轴</Button>} />
            )}
          </LoadingHandoff>
        </div>
      </div>
    </div>
  );
}


// ── 极简 Markdown ────────────────────────────────────────────

type Block =
  | { kind: "h1" | "h2" | "h3"; text: string }
  | { kind: "p"; text: string }
  | { kind: "ul" | "ol"; items: string[] }
  | { kind: "quote"; text: string }
  | { kind: "code"; text: string }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "hr" };

const BASE = {
  margin: 0,
  fontSize: "var(--text-sm)",
  lineHeight: "var(--leading-normal)" as const,
};

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((s) => s.trim());
}

function parse(src: string): Block[] {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const out: Block[] = [];
  let i = 0;

  const isBlockStart = (l: string) =>
    /^(#{1,3}\s|[-*+]\s|\d+[.)]\s|>|\||```|[-*_]{3,}\s*$)/.test(l);

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i++;
      continue;
    }

    if (line.trimStart().startsWith("```")) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trimStart().startsWith("```")) {
        body.push(lines[i]);
        i++;
      }
      i++;
      out.push({ kind: "code", text: body.join("\n") });
      continue;
    }

    // 表格：| a | b | 后跟 | --- | --- |
    if (line.trim().startsWith("|") && (lines[i + 1] ?? "").includes("---")) {
      const header = splitRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      out.push({ kind: "table", header, rows });
      continue;
    }

    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      const kind = h[1].length === 1 ? "h1" : h[1].length === 2 ? "h2" : "h3";
      out.push({ kind: kind as "h1" | "h2" | "h3", text: h[2] });
      i++;
      continue;
    }

    if (/^[-*_]{3,}\s*$/.test(line.trim())) {
      out.push({ kind: "hr" });
      i++;
      continue;
    }

    if (line.trimStart().startsWith(">")) {
      out.push({ kind: "quote", text: line.trimStart().slice(1).trim() });
      i++;
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, ""));
        i++;
      }
      out.push({ kind: "ul", items });
      continue;
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ""));
        i++;
      }
      out.push({ kind: "ol", items });
      continue;
    }

    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) {
      para.push(lines[i]);
      i++;
    }
    if (para.length) out.push({ kind: "p", text: para.join(" ") });
  }

  return out;
}

/** 行内：**粗体**、`代码` */
type EvidenceAction = (id: number) => (() => void) | undefined;

function inline(text: string, key: string, onEvidence?: EvidenceAction): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[活动 #\d+\])/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let n = 0;

  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      parts.push(
        <strong key={`${key}-b${n++}`} style={{ fontWeight: "var(--weight-semibold)" }}>
          {tok.slice(2, -2)}
        </strong>
      );
    } else if (tok.startsWith("[活动 #")) {
      const active = onEvidence?.(Number(tok.slice(5, -1)));
      parts.push(active
        ? <button key={`${key}-e${n++}`} className="df-evidence-link" onClick={active}>{tok.slice(1, -1)}</button>
        : tok);
    } else {
      parts.push(
        <code
          key={`${key}-c${n++}`}
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.9em",
            background: "var(--bg-sunken)",
            padding: "1px 5px",
            borderRadius: "var(--radius-xs)",
            color: "var(--accent-text)",
          }}
        >
          {tok.slice(1, -1)}
        </code>
      );
    }
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function renderBlock(b: Block, i: number, onEvidence?: EvidenceAction) {
  switch (b.kind) {
    case "h1":
      return (
        <h1
          key={i}
          style={{
            ...BASE,
            fontSize: "var(--text-xl)",
            marginTop: "var(--space-6)",
            marginBottom: "var(--space-3)",
          }}
        >
          {inline(b.text, `h1-${i}`, onEvidence)}
        </h1>
      );
    case "h2":
      return (
        <h2
          key={i}
          style={{
            ...BASE,
            fontSize: "var(--text-lg)",
            marginTop: "var(--space-6)",
            marginBottom: "var(--space-2)",
            paddingBottom: "var(--space-2)",
            borderBottom: "1px solid var(--border-subtle)",
          }}
        >
          {inline(b.text, `h2-${i}`, onEvidence)}
        </h2>
      );
    case "h3":
      return (
        <h3
          key={i}
          style={{
            ...BASE,
            fontSize: "var(--text-md)",
            fontWeight: "var(--weight-semibold)",
            marginTop: "var(--space-4)",
            marginBottom: "var(--space-2)",
          }}
        >
          {inline(b.text, `h3-${i}`, onEvidence)}
        </h3>
      );
    case "p":
      return (
        <p
          key={i}
          style={{ ...BASE, color: "var(--text-secondary)", marginBottom: "var(--space-3)" }}
        >
          {inline(b.text, `p-${i}`, onEvidence)}
        </p>
      );
    case "ul":
      return (
        <ul
          key={i}
          style={{ ...BASE, paddingLeft: "var(--space-5)", marginBottom: "var(--space-3)" }}
        >
          {b.items.map((it, k) => (
            <li key={k} style={{ marginBottom: 4, color: "var(--text-secondary)" }}>
              <span aria-hidden style={{ color: "var(--text-placeholder)", marginRight: 6 }}>
                ·
              </span>
              {inline(it, `ul-${i}-${k}`, onEvidence)}
            </li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol
          key={i}
          style={{
            ...BASE,
            paddingLeft: "var(--space-5)",
            marginBottom: "var(--space-3)",
            listStyle: "decimal",
          }}
        >
          {b.items.map((it, k) => (
            <li key={k} style={{ marginBottom: 4, color: "var(--text-secondary)" }}>
              {inline(it, `ol-${i}-${k}`, onEvidence)}
            </li>
          ))}
        </ol>
      );
    case "quote":
      return (
        <blockquote
          key={i}
          style={{
            ...BASE,
            margin: "0 0 var(--space-3)",
            padding: "var(--space-3) var(--space-4)",
            borderLeft: "3px solid var(--accent)",
            background: "var(--accent-subtle)",
            borderRadius: "var(--radius-sm)",
            color: "var(--text-secondary)",
          }}
        >
          {inline(b.text, `q-${i}`, onEvidence)}
        </blockquote>
      );
    case "code":
      return (
        <pre
          key={i}
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-xs)",
            background: "var(--bg-sunken)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-3)",
            overflowX: "auto",
            margin: "0 0 var(--space-3)",
          }}
        >
          {b.text}
        </pre>
      );
    case "hr":
      return (
        <hr
          key={i}
          style={{
            border: "none",
            borderTop: "1px solid var(--border-subtle)",
            margin: "var(--space-6) 0",
          }}
        />
      );
    case "table":
      return (
        <div key={i} style={{ overflowX: "auto", marginBottom: "var(--space-4)" }}>
          <table
            style={{ borderCollapse: "collapse", width: "100%", fontSize: "var(--text-sm)" }}
          >
            <thead>
              <tr>
                {b.header.map((h, k) => (
                  <th
                    key={k}
                    style={{
                      textAlign: "left",
                      padding: "var(--space-2) var(--space-3)",
                      borderBottom: "1px solid var(--border-default)",
                      color: "var(--text-primary)",
                      fontWeight: "var(--weight-semibold)",
                      fontSize: "var(--text-xs)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {inline(h, `th-${i}-${k}`, onEvidence)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {b.rows.map((r, k) => (
                <tr key={k}>
                  {r.map((c, j) => (
                    <td
                      key={j}
                      style={{
                        padding: "var(--space-2) var(--space-3)",
                        borderBottom: "1px solid var(--border-subtle)",
                        color: "var(--text-secondary)",
                      }}
                    >
                      {inline(c, `td-${i}-${k}-${j}`, onEvidence)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
  }
}

function Markdown({ source, onEvidence }: { source: string; onEvidence?: EvidenceAction }) {
  const blocks = useMemo(() => parse(source), [source]);
  return <div>{blocks.map((block, index) => renderBlock(block, index, onEvidence))}</div>;
}
