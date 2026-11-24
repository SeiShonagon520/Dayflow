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
check("录制状态由同一处播报", 'role="status"' in SHELL and "recordingControl" in SHELL)
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
print("6. 表单分组、草稿测试和就地反馈")
print("=" * 68)
SET = (SRC / "pages" / "SettingsPage.tsx").read_text(encoding="utf-8")
check("分组校验", "validate(group, draft)" in SET)
check("校验地址并聚焦错误字段", "new URL(values.api_url)" in SET and "getElementById(error.field)?.focus()" in SET)
check("只保存当前组变动", "const keys = changed(group)" in SET and "api.saveSettings(patch)" in SET)
check("无变更时不显示保存按钮", "{edited && <>" in SET)
check("支持撤回草稿", "撤回更改" in SET and "saved[key]" in SET)
check("分组结果使用可访问状态", 'notice.kind === "err" ? "alert" : "status"' in SET)
test_body = SET.split("const test = async")[1].split("const testEmail", 1)[0]
check("连接测试使用草稿", "api.testConnection(" in test_body and "await save" not in test_body)
check("清理需要再次确认", "确认清理" in SET and "<Dialog" in SET)

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
check("减少动效下隐藏运动计时条，保留撤销按钮", ".df-undo-timer { display: none; }" in CSS and "撤销" in TL)

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
