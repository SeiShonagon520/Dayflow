"""Interaction system tests.

Each check corresponds to a failure measured in a real browser.
None of them are visible to a keyword search.
"""
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SRC = Path(__file__).resolve().parent.parent / "src"
CSS = (SRC / "styles" / "global.css").read_text(encoding="utf-8")
TOKENS = (SRC / "styles" / "tokens.css").read_text(encoding="utf-8")
UI = (SRC / "components" / "ui.tsx").read_text(encoding="utf-8")
SHELL = (SRC / "components" / "Shell.tsx").read_text(encoding="utf-8")
DIALOG = (SRC / "components" / "Dialog.tsx").read_text(encoding="utf-8")
STATS = (SRC / "pages" / "StatsPage.tsx").read_text(encoding="utf-8")
MOTION = (SRC / "components" / "MotionControl.tsx").read_text(encoding="utf-8")
TL = (SRC / "pages" / "TimelinePage.tsx").read_text(encoding="utf-8")
REPORTS = (SRC / "pages" / "ReportsPage.tsx").read_text(encoding="utf-8")

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}"
          + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(name)


print("=" * 68)
print("1. 模态必须困住焦点（实测修复前 25 次 Tab 就逃出去了）")
print("=" * 68)
check("Dialog 组件存在", DIALOG != "")
check("背景加 inert", 'setAttribute("inert"' in DIALOG)
check("Tab 到末尾回到开头", "preventDefault" in DIALOG and
      "lastItem.focus()" in DIALOG and "firstItem.focus()" in DIALOG)
check("Shift+Tab 到开头跳到末尾", "shiftKey" in DIALOG)
check("关闭后焦点归还", "restoreTo" in DIALOG and
      "restoreTo.current?.focus" in DIALOG)
check("Esc 关闭", 'e.key === "Escape"' in DIALOG)
check("面板用 portal 挂到 body", "createPortal" in DIALOG)
check("面板自身可接收焦点", "tabIndex={-1}" in DIALOG)
check("清理时移除 inert", 'removeAttribute("inert")' in DIALOG)

print()
print("=" * 68)
print("2. 命中区（实测 58 个元素全部小于 40px）")
print("=" * 68)
for cls, why in [("df-hit-v", "纵向扩展"),
                 ("df-hit::before", "双向扩展"),
                 ("df-hit-toggle::before", "开关专用")]:
    check(f".{cls} 已定义（{why}）", cls in CSS)
check("sm 和 md 按钮都挂了命中区 class",
      'size === "lg" ? "" : " df-hit-v"' in UI)
check("IconButton 挂命中区", "df-hit-v" in TL)
check("筛选药丸挂命中区", "df-hit-v" in TL)
check("Toggle 挂命中区", "df-hit-toggle" in UI)
check("指针交互设了 touch-action",
      "touchAction" in UI and "touchAction" in TL)
check("伪元素不挂在 input 上",
      not re.search(r"<input[^>]*df-hit", TL, re.S))

print()
print("=" * 68)
print("3. 表单控件本身够高（伪元素扩不了 input）")
print("=" * 68)
m = re.search(r"\.df-field\s*\{(.*?)\}", CSS, re.S)
check(".df-field 定义了高度 ≥40", bool(m) and
      re.search(r"height:\s*4\d", m.group(1)) is not None,
      m.group(1).strip().replace("\n", " ") if m else "")
seg = UI.split("export const Input")[1].split("export function Toggle")[0]
check("Input 不写内联 height", "height: 34" not in seg)
check("Input 挂了 df-field", "df-field" in seg)

print()
print("=" * 68)
print("4. 状态变化要被播报（实测页面上一条 live region 都没有）")
print("=" * 68)
check("Shell 有录制状态 live region",
      'aria-live="polite"' in SHELL and "role=\"status\"" in SHELL)
check("撤销条是 live region", 'aria-live="polite"' in TL)

print()
print("=" * 68)
print("5. 键盘路径：分组控件用方向键，不用 Tab")
print("=" * 68)
check("Segmented 声明了 role=tablist", 'role="tablist"' in STATS)
check("Segmented 支持左右方向键",
      "ArrowRight" in STATS and "ArrowLeft" in STATS)
check("Segmented 有 aria-label", "aria-label={label}" in STATS)
check("Segmented 只让选中项可 Tab", "tabIndex={active ? 0 : -1}" in STATS)
check("radiogroup 支持方向键",
      "ArrowDown" in MOTION and "ArrowUp" in MOTION)
check("radiogroup 只让选中项可 Tab",
      "tabIndex={active ? 0 : -1}" in MOTION)
check("日报列表选中态有 aria-current",
      "aria-current" in REPORTS)
check("日报列表选中态有非颜色信号", "●" in REPORTS)

print()
print("=" * 68)
print("6. 表单：校验、错误可见、不 disabled 到有效")
print("=" * 68)
SET = (SRC / "pages" / "SettingsPage.tsx").read_text(encoding="utf-8")
check("有 validate 函数", "const validate" in SET)
check("校验 API 地址", "API 地址不能为空" in SET)
check("校验 URL 协议", "http:// 或 https://" in SET)
check("校验数值范围", "每日目标要在 1 到 24 小时之间" in SET)
check("保存前先校验", "const errs = validate(s)" in SET)
check("校验失败不发请求", "if (errs.length > 0)" in SET)
check("错误消息不做截断", 'msg.kind === "err" ? "normal"' in SET)
# 规范：submit 不能 disabled 到表单有效。
# 只看代码行 —— 解释这件事的注释里正好写着这个字符串。
SET_CODE = re.sub(r"/\*.*?\*/", "", SET, flags=re.S)
check("保存按钮不再 disabled={!dirty}",
      "disabled={!dirty}" not in SET_CODE)
check("没改动时有解释", "没有需要保存的改动" in SET)
check("错误用 assertive 播报", 'aria-live={msg.kind === "err"' in SET)
check("焦点送到出错字段", "document.getElementById(first.id)?.focus()" in SET)
# FIELDS 的 id 必须是真实存在的字段，否则焦点落空
for fid in re.findall(r'\{ id: "([\w-]+)"', SET):
    check(f"字段 #{fid} 存在", f'id="{fid}"' in SET)
# test() 也要校验，否则用户看到「连接失败」实际是表单没填对
test_body = SET.split("const test = async")[1][:900]
check("测试连接前也校验", "validate(s)" in test_body)

print()
print("=" * 68)
print("7. 撤销倒计时（用户不知道还剩多久）")
print("=" * 68)
check("有 df-undo-timer 样式", ".df-undo-timer {" in CSS)
check("--undo-window token", "--undo-window:" in TOKENS)
m_u = re.search(r"const UNDO_MS\s*=\s*(\d+)", TL)
m_w = re.search(r"--undo-window:\s*(\d+)ms", TOKENS)
check("JS 和 CSS 的撤销窗口一致",
      bool(m_u and m_w) and int(m_u.group(1)) == int(m_w.group(1)),
      f"js={m_u.group(1) if m_u else '?'} "
      f"css={m_w.group(1) if m_w else '?'}")
check("倒计时条是纯装饰（不参与播报）",
      'aria-hidden' in TL and "df-undo-timer" in TL)
# 减少动效下砍成 0.01ms 会让条子瞬间缩到 0（实测），
# 比没有更糟 —— 换成步进，形状仍随时间变化
check("reduce 下倒计时保留为步进", "df-undo-timer-steps" in CSS)

print()
print("=" * 68)
print("结果")
print("=" * 68)
if failures:
    print(f"{len(failures)} 项未通过:")
    for f in failures:
        print("  -", f)
    raise SystemExit(1)
print("全部通过")
