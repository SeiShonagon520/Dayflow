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

import { useEffect, useMemo, useState } from "react";
import { ApiError, api, saveTextFile } from "@/lib/api";
import { fullDate, prettyDate, todayStr, weekdayOf } from "@/lib/format";
import { Button, EmptyState, SectionTitle, Spinner } from "@/components/ui";
import { useIsPhone } from "@/lib/useMediaQuery";
import { FocusRing } from "@/components/FocusRing";
import { TimelineSignature } from "@/components/TimelineSignature";

export function ReportsPage() {
  const [dates, setDates] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");

  const loadDates = async () => {
    try {
      const res = await api.getReportDates();
      /* 后端字段缺失时不要让整个白屏。
         之前直接用 dates.length，一个 undefined 就能让整个应用崩溃 ——
         实测 320px 下切到日报页，.df-shell 直接从 DOM 消失。 */
      const dates = Array.isArray(res?.dates) ? res.dates : [];
      setDates(dates);
      if (dates.length > 0) setSelected((cur) => cur ?? dates[0]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDates();
  }, []);

  useEffect(() => {
    if (!selected) return;
    setError(null);
    let cancelled = false;
    (async () => {
      try {
        const r = await api.getReport(selected);
        if (!cancelled) setContent(r.content);
      } catch {
        if (!cancelled) setContent("");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const generate = async () => {
    const date = selected ?? todayStr();
    setGenerating(true);
    setError(null);
    setStatus("");
    try {
      const r = await api.generateReport(date);
      setContent(r.content);
      setSelected(date);
      setStatus("日报已生成");
      await loadDates();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  };

  const copy = async () => {
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      setStatus("已复制到剪贴板");
    } catch {
      setError("复制失败，请手动选择文本复制");
    }
  };

  const exportMd = async () => {
    if (!content || !selected) return;
    const path = await saveTextFile(
      `日报_${selected}.md`,
      content,
      "Markdown (*.md);;文本 (*.txt)"
    );
    setStatus(path ? "已导出" : "已取消导出");
  };

  const today = todayStr();
  const noContent = !content;

  const phone = useIsPhone();

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* ── 工具栏 ─────────────────────────────────── */}
      <div
        className="df-toolbar"
        data-stacked={phone ? "true" : "false"}
      >
        <div className="df-toolbar-row">
          <TimelineSignature />
          <h2 className="df-page-title">日报</h2>
          <span
            className="df-page-subtitle"
            style={{
              fontSize: "var(--text-sm)",
              color: "var(--text-tertiary)",
            }}
          >
            {dates.length > 0 ? `${dates.length} 篇` : "还没有生成过"}
          </span>
          <div className="df-toolbar-spacer" />
          {status && (
            <span style={{ fontSize: "var(--text-xs)", color: "var(--success)" }}>
              {status}
            </span>
          )}
          <Button
            size="sm"
            onClick={copy}
            disabled={noContent}
            title={noContent ? "还没有日报内容可复制" : "复制全文"}
          >
            复制
          </Button>
          <Button
            size="sm"
            onClick={exportMd}
            disabled={noContent}
            title={noContent ? "还没有日报内容可导出" : "导出为 Markdown"}
          >
            导出
          </Button>
          <Button
            variant={noContent ? "secondary" : "primary"}
            size="sm"
            onClick={generate}
            loading={generating}
          >
            {generating ? "生成中" : "生成日报"}
          </Button>
        </div>
      </div>

      <div
        className="df-split"
        data-stacked={phone ? "true" : "false"}
        style={{ flex: 1, display: "flex", minHeight: 0 }}
      >
        {/* ── 日期列表 ─────────────────────────────── */}
        <div
          className="df-split-aside"
          style={{
            flexShrink: 0,
            borderRight: "1px solid var(--border-subtle)",
            overflowY: "auto",
            padding: "var(--space-3)",
          }}
        >
          <SectionTitle
            action={
              <button
                onClick={() => setSelected(today)}
                /* 24×18 的裸文字按钮太小。伪元素扩纵向到 40px，
                   横向也扩 —— 左右都没有紧邻控件。 */
                className="df-hit"
                style={{
                  fontSize: "var(--text-xs)",
                  color: "var(--accent-text)",
                  position: "relative",
                  touchAction: "manipulation",
                }}
              >
                今天
                <FocusRing />
              </button>
            }
          >
            已生成
          </SectionTitle>

          {loading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: 20 }}>
              <Spinner size={16} />
            </div>
          ) : dates.length === 0 ? (
            <p
              style={{
                fontSize: "var(--text-xs)",
                color: "var(--text-tertiary)",
                padding: 8,
              }}
            >
              还没有任何日报
            </p>
          ) : (
            dates.map((d) => {
              const active = d === selected;
              return (
                <button
                  key={d}
                  onClick={() => setSelected(d)}
                  /* 选中态用 aria-current 表达，不只靠背景色 */
                  aria-current={active ? "true" : undefined}
                  className="df-hit-v"
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "var(--space-2) var(--space-3)",
                    borderRadius: "var(--radius-md)",
                    background: active ? "var(--accent-subtle)" : "transparent",
                    marginBottom: 2,
                    position: "relative",
                    touchAction: "manipulation",
                  }}
                >
                  <div
                    style={{
                      fontSize: "var(--text-sm)",
                      fontWeight: active
                        ? "var(--weight-semibold)"
                        : "var(--weight-normal)",
                      color: active ? "var(--accent)" : "var(--text-primary)",
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    {/* 选中标记：颜色之外再给一个形状信号 */}
                    {active && (
                      <span aria-hidden style={{ fontSize: "var(--text-2xs)" }}>
                        ●
                      </span>
                    )}
                    {prettyDate(d)}
                  </div>
                  <div style={{ fontSize: "var(--text-2xs)", color: "var(--text-tertiary)" }}>
                    {weekdayOf(d)}
                  </div>
                  <FocusRing />
                </button>
              );
            })
          )}
        </div>

        {/* ── 内容 ─────────────────────────────────── */}
        <div style={{ flex: 1, overflowY: "auto", minWidth: 0 }}>
          {error && !content ? (
            <EmptyState
              icon="⚠️"
              title="生成失败"
              description={error}
              action={
                <div style={{ display: "flex", gap: "var(--space-2)" }}>
                  <Button onClick={generate}>重试</Button>
                  <Button variant="secondary" onClick={() => setError(null)}>返回</Button>
                </div>
              }
            />
          ) : !selected ? (
            <EmptyState
              icon="📋"
              title="选择或生成一篇日报"
              description={
                "日报会汇总当天的活动记录、时间分配和专注时段。\n点击右上角「生成日报」让 AI 写一篇。"
              }
              action={
                <Button variant="primary" onClick={generate}>
                  生成今天的日报
                </Button>
              }
            />
          ) : !content ? (
            <EmptyState
              icon="📄"
              title={`${prettyDate(selected)} 还没有日报`}
              description={
                "点击「生成日报」让 AI 汇总这一天的活动。\n如果时间轴还是空的，先开始录制。"
              }
              action={
                <Button variant="primary" onClick={generate}>
                  生成这篇日报
                </Button>
              }
            />
          ) : (
            <>
              {error && (
                <div
                  style={{
                    maxWidth: 720,
                    margin: "var(--space-4) auto 0",
                    padding: "var(--space-2) var(--space-4)",
                    background: "var(--danger-bg)",
                    border: "1px solid var(--danger)",
                    borderRadius: "var(--radius-md)",
                    color: "var(--danger)",
                    fontSize: "var(--text-xs)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <span>{error}</span>
                  <Button size="sm" variant="ghost" onClick={() => setError(null)}>
                    关闭
                  </Button>
                </div>
              )}
              <article
                style={{
                  maxWidth: 720,
                  margin: "0 auto",
                  padding: "var(--space-8) var(--space-6)",
                }}
              >
              <div
                style={{
                  fontSize: "var(--text-xs)",
                  color: "var(--text-tertiary)",
                  marginBottom: "var(--space-5)",
                  paddingBottom: "var(--space-3)",
                  borderBottom: "1px solid var(--border-subtle)",
                }}
              >
                {fullDate(selected)}
              </div>
              <Markdown source={content} />
            </article>
          </>
        )}
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
