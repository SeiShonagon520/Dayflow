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
import { api, saveTextFile } from "@/lib/api";
import { fullDate, prettyDate, todayStr, weekdayOf } from "@/lib/format";
import { Button, EmptyState, SectionTitle, Spinner } from "@/components/ui";
import { useLatest } from "@/lib/useLatest";
import { LoadingHandoff } from "@/components/LoadingHandoff";
import { useIsPhone } from "@/lib/useMediaQuery";
import { FocusRing } from "@/components/FocusRing";
import { TimelineSignature } from "@/components/TimelineSignature";

export function ReportsPage({
  initialDate, active, onOpenTimeline,
}: {
  initialDate: { day: string } | null;
  active: boolean;
  onOpenTimeline: (day: string) => void;
}) {
  const today = todayStr();
  const [dates, setDates] = useState<string[]>([]);
  const [selected, setSelected] = useState(() => initialDate?.day ?? today);
  const [report, setReport] = useState<{ date: string; content: string; hasActivity: boolean } | null>(null);
  const [readError, setReadError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [dateError, setDateError] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error?: boolean } | null>(null);
  const [generating, setGenerating] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const selection = useLatest(selected);
  const readRequest = useRef(0);
  const generationLock = useRef(false);
  const phone = useIsPhone();

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
    setNotice(null);
    void loadReport(selected);
    return () => { ++readRequest.current; };
  }, [active, selected]);

  const current = report?.date === selected ? report : null;
  const content = current?.content ?? "";
  const reportDays = Array.from(new Set([today, selected, ...dates])).sort().reverse();

  useEffect(() => {
    if (!active || selected !== today || !current || current.hasActivity || readError) return;
    const timer = window.setInterval(() => { if (!document.hidden) void loadReport(selected); }, 8000);
    return () => window.clearInterval(timer);
  }, [active, selected, today, current?.hasActivity, readError]);

  const retry = async () => {
    setRetrying(true);
    await loadReport(selected);
    setRetrying(false);
  };

  const showError = (error: unknown, fallback: string) => {
    setNotice({ text: error instanceof Error ? error.message : fallback, error: true });
  };

  const generate = async () => {
    if (generationLock.current || !current?.hasActivity) return;
    generationLock.current = true;
    const day = selected;
    setGenerating(day);
    setNotice(null);
    try {
      const next = await api.generateReport(day);
      if (selection.current === day) {
        ++readRequest.current;
        setReadError("");
        setReport({ date: day, content: next.content, hasActivity: true });
        setNotice({ text: "日报已生成" });
      }
      void loadDates();
    } catch (error) {
      if (selection.current === day) showError(error, "生成日报失败，请重试");
    } finally {
      generationLock.current = false;
      setGenerating(null);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setNotice({ text: "已复制日报" });
    } catch {
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
            <Button size="sm" onClick={copy}>复制日报</Button>
            <Button size="sm" onClick={exportMd} loading={exporting}>保存文件</Button>
          </>}
        </div>
      </div>

      <div className="df-split" data-stacked={phone ? "true" : "false"}
        style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div className="df-split-aside"
          style={{ flexShrink: 0, borderRight: "1px solid var(--border-subtle)", overflowY: "auto", padding: "var(--space-3)" }}>
          <SectionTitle>日期</SectionTitle>
          {reportDays.map((day) => (
            <button key={day} onClick={() => setSelected(day)}
              aria-current={day === selected ? "true" : undefined}
              className="df-hit-v df-report-date">
              <span className="df-selection-mark" aria-hidden>●</span>
              {day === today ? "今天" : prettyDate(day)}
              <span className="df-report-weekday">{weekdayOf(day)}</span>
              <FocusRing />
            </button>
          ))}
          {dateError && <Button size="sm" variant="ghost" onClick={loadDates}>重试读取日期</Button>}
        </div>

        <div style={{ flex: 1, overflowY: "auto", minWidth: 0 }} key={selected}>
          {generating && generating !== selected && (
            <p className="df-context-note" role="status">正在生成 {prettyDate(generating)} 的日报，可以先阅读其他日报。</p>
          )}
          {notice && (
            <p className="df-context-note df-feedback" role={notice.error ? "alert" : "status"}
              data-error={notice.error || undefined}>{notice.text}</p>
          )}
          {readError && content && <div className="df-inline-notice" role="alert">
            <span>刷新失败，当前仍显示已打开的日报。</span>
            <Button size="sm" onClick={retry} loading={retrying}>重试读取</Button>
          </div>}
          <LoadingHandoff loading={(!current && !readError) || (retrying && !content)}
            skeleton={<div className="df-wait"><Spinner />正在读取日报</div>}>
            {readError && !content ? (
              <EmptyState icon="⚠️" title="日报读取失败" description={readError}
                action={<Button onClick={retry}>重试读取</Button>} />
            ) : content ? (
              <article style={{ maxWidth: 720, margin: "0 auto", padding: "var(--space-5) var(--space-6)" }}>
                <p className="df-report-weekday">{fullDate(selected)}</p>
                <Markdown source={content} />
                <details className="df-details">
                  <summary>重新生成</summary>
                  <p>重新生成会替换这篇日报。需要保留原文时，可先保存文件。</p>
                  <Button size="sm" onClick={generate} loading={generating === selected}
                    disabled={!!generating && generating !== selected}>生成并替换</Button>
                </details>
              </article>
            ) : current?.hasActivity ? (
              <EmptyState icon="📄" title="这一天的日报尚未生成"
                description="用这一天的活动记录整理一份总结。"
                action={<Button variant="primary" loading={generating === selected}
                  disabled={!!generating && generating !== selected} onClick={generate}>生成日报</Button>} />
            ) : (
              <EmptyState icon="📋" title={selected === today ? "今天还没有可汇总的活动" : "这一天没有可汇总的活动"}
                description={selected === today ? "录制并分析后，就可以在这里生成日报。" : "可以查看这一天的时间轴，或选择其他日期。"}
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
function inline(text: string, key: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
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

function renderBlock(b: Block, i: number) {
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
          {inline(b.text, `h1-${i}`)}
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
          {inline(b.text, `h2-${i}`)}
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
          {inline(b.text, `h3-${i}`)}
        </h3>
      );
    case "p":
      return (
        <p
          key={i}
          style={{ ...BASE, color: "var(--text-secondary)", marginBottom: "var(--space-3)" }}
        >
          {inline(b.text, `p-${i}`)}
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
              {inline(it, `ul-${i}-${k}`)}
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
              {inline(it, `ol-${i}-${k}`)}
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
          {inline(b.text, `q-${i}`)}
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
                    {inline(h, `th-${i}-${k}`)}
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
                      {inline(c, `td-${i}-${k}-${j}`)}
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

function Markdown({ source }: { source: string }) {
  const blocks = useMemo(() => parse(source), [source]);
  return <div>{blocks.map(renderBlock)}</div>;
}
