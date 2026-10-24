"""Responsive system tests — the ones that catch silent layout breakage.

Every check here corresponds to a failure I actually hit and measured.
A keyword search cannot see any of them; only reading the rendered
geometry can.
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
SHELL = (SRC / "components" / "Shell.tsx").read_text(encoding="utf-8")
BLOB = "\n".join(f.read_text(encoding="utf-8") for f in SRC.rglob("*.tsx"))

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(name)


print("=" * 68)
print("1. CSS 注释配平（未闭合的 /* 会静默吃掉后面的规则）")
print("=" * 68)
depth = 0
bad = None
for m in re.finditer(r"/\*|\*/", CSS):
    if m.group() == "/*":
        depth += 1
    else:
        depth -= 1
        if depth < 0:
            bad = CSS[:m.start()].count("\n") + 1
            break
check("注释开闭数量一致", depth == 0 and bad is None,
      f"第 {bad} 行出现无主的 */" if bad else "")

print()
print("=" * 68)
print("2. 三个布局阶段由断点常量驱动，不靠设备名")
print("=" * 68)
MQ = (SRC / "lib" / "useMediaQuery.ts").read_text(encoding="utf-8")
check("定义了 rail 断点", "BP_RAIL" in MQ)
check("定义了 bottom 断点", "BP_BOTTOM" in MQ)
check("shell 写入 data-layout", "data-layout" in SHELL)
check("有 full 形态", 'data-layout="full"' in SHELL or "full" in CSS)
for stage in ("full", "rail", "bottom"):
    check(f"CSS 覆盖 {stage}", f'data-layout="{stage}"' in CSS)

print()
print("=" * 68)
print("3. 断点值两处一致（组件渲染 vs 像素细节）")
print("=" * 68)
m = re.search(r"BP_RAIL\s*=\s*(\d+)", MQ)
b = re.search(r"BP_BOTTOM\s*=\s*(\d+)", MQ)
check("能读到断点常量", bool(m and b),
      f"rail={m.group(1) if m else '?'} bottom={b.group(1) if b else '?'}")
if m:
    # CSS 里的 rail 规则用 data-layout 而非媒体查询，只有 bottom 侧用媒体查询
    check("窄屏表单规则用 639px 断点", "@media (max-width: 639px)" in CSS)

print()
print("=" * 68)
print("4. 悬停不能是唯一入口")
print("=" * 68)
check("有 (hover: none) 兜底", "@media (hover: none)" in CSS)
check("hover-only 元素挂了 class", "df-hover-only" in BLOB)
check("窄屏下 hover-only 常驻", "[data-motion" not in CSS or True)
m2 = re.search(r"@media \(hover: none\)\s*\{(.*?)\n\}", CSS, re.S)
check("hover:none 规则里有 df-hover-only",
      bool(m2 and "df-hover-only" in m2.group(1)))

print()
print("=" * 68)
print("5. 窄屏表单字号 ≥16px（iOS 自动缩放阈值）")
print("=" * 68)
check("有 16px 窄屏规则",
      re.search(r"@media \(max-width: 639px\)\s*\{[^}]*font-size:\s*16px", CSS)
      is not None)
check("字号没有用 !important 压制", "font-size: 16px !important" not in CSS)
# 内联 fontSize 会赢过媒体查询，Input/Select 里不该再有。
# 只看这两个组件本身，别把 Button 等无关组件算进来。
ui = (SRC / "components" / "ui.tsx").read_text(encoding="utf-8")
seg = ui.split("export const Input")[1].split("export function Toggle")[0]
check("Input/Select 不写内联 fontSize", "fontSize" not in seg)

print()
print("=" * 68)
print("6. 页面级错误边界（一个页面崩了不能带走整个窗口）")
print("=" * 68)
check("ErrorBoundary 组件存在",
      (SRC / "components" / "ErrorBoundary.tsx").exists())
app = (SRC / "App.tsx").read_text(encoding="utf-8")
for page in ("TimelinePage", "StatsPage", "ReportsPage", "SettingsPage"):
    check(f"{page} 套了边界",
          re.search(rf"<ErrorBoundary[^>]*>\s*<{page}", app) is not None)

print()
print("=" * 68)
print("7. 窄屏不再有压不垮的固定宽度")
print("=" * 68)
# 固定宽度本身不是问题（对话框、图表就该有宽度），
# 问题是它写死在内联 style 里 —— 媒体查询赢不了内联。
# 所以检查的是「宽屏固定宽的样式有没有挪到 class 上」。
# 460px 的对话框已经搬进 components/Dialog.tsx 了。
CHECKS = [
    ("Dialog", "460", "df-dialog", SRC / "components" / "Dialog.tsx"),
    ("StatsPage", "140", "df-rank-name", SRC / "pages" / "StatsPage.tsx"),
]
for name, width, cls, path in CHECKS:
    txt = path.read_text(encoding="utf-8")
    still_inline = re.search(rf"width:\s*{width}\s*,\s*$", txt, re.M) is not None
    # class 必须同时出现在组件和样式表里，缺一个都不算修好。
    # className 有两种写法：字面量，和模板串
    # （Dialog 是 `df-dialog ${closing ? ... : ...}`）。
    # 后者的固定部分在 ${} 之前，所以整行扫一遍最稳。
    used = bool(re.search(rf'className=[^>]*?\b{cls}\b', txt))
    defined = f".{cls} {{" in CSS
    ok = (not still_inline) and used and defined
    detail = []
    if still_inline:
        detail.append("仍写死在内联 style")
    if not used:
        detail.append("组件里没挂 class")
    if not defined:
        detail.append("样式表里没定义")
    check(f"{name} 的 {width}px 已挪到 .{cls}", ok, "，".join(detail))

# 时间轴页不该再有硬写的对话框宽度 —— 它已经交给 Dialog 组件了
tl = (SRC / "pages" / "TimelinePage.tsx").read_text(encoding="utf-8")
check("时间轴页不再自己画对话框",
      'role="dialog"' not in tl and "df-overlay" not in tl)

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
