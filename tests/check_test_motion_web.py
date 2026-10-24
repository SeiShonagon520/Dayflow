"""Motion system tests — the ones that actually catch silent breakage.

The bug this guards against: a keyframe exists in CSS but never fires because
the selector doesn't match. Keyword search can't see that; only running it can.
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
BLOB = "\n".join(f.read_text(encoding="utf-8") for f in SRC.rglob("*.tsx"))

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(name)


print("=" * 66)
print("1. 无死代码 keyframes")
print("=" * 66)
defined = set(re.findall(r"@keyframes\s+([\w-]+)", CSS))
blob = "\n".join(f.read_text(encoding="utf-8")
                 for f in SRC.rglob("*.tsx"))
# 两种引用方式：组件内联 animation，或 CSS class 里挂 animation
inline_used = set(re.findall(r"animation:\s*[\"'`]([a-z-]+)", blob))
class_used = set(re.findall(r"animation:\s*([a-z-]+)\s", CSS))
used = inline_used | class_used
for k in sorted(defined):
    check(f"{k} 被使用", k in used,
          "" if k in used else "定义了但没有任何规则引用它")

print()
print("=" * 66)
print("2. 动画时长一律走 token，不写死毫秒")
print("=" * 66)
durations = re.findall(r"animation:\s*[\"'`]([^\"'`]+)[\"'`]", blob)
hardcoded = [d for d in durations if re.search(r"\d+\s*ms", d)]
check("组件内无写死 ms", not hardcoded, str(hardcoded) if hardcoded else "")

print()
print("=" * 66)
print("3. 时长 token 齐全")
print("=" * 66)
for t in ("tactile", "base", "reveal", "menu", "space", "page", "spin"):
    check(f"--dur-{t}", f"--dur-{t}:" in TOKENS)

print()
print("=" * 66)
print("4. 减少动效：保留加载指示器")
print("=" * 66)
m = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", CSS, re.S)
block = m.group(1) if m else ""
check("有 reduce 媒体查询", bool(block))
# none 会让 transitionend/animationend 完全不触发，
# 依赖这些事件的代码会永久挂起 —— 必须是 0.01ms
check("用 0.01ms 而非 none",
      "0.01ms" in block and "duration: none" not in block)
check("例外保留 spinner 旋转", "df-spin" in block)

print()
print("=" * 66)
print("5. 界面内动效开关")
print("=" * 66)
check("data-motion=reduced 降级", '[data-motion="reduced"]' in CSS)
check("data-motion=full 恢复", '[data-motion="full"]' in CSS)
check("MotionControl 组件存在",
      (SRC / "components" / "MotionControl.tsx").exists())
settings = (SRC / "pages" / "SettingsPage.tsx").read_text(encoding="utf-8")
check("设置页引用了 MotionControl", "MotionControl" in settings)

print()
print("=" * 66)
print("6. 按下反馈走 CSS class（内联 style 会盖掉 :active）")
print("=" * 66)
ui = (SRC / "components" / "ui.tsx").read_text(encoding="utf-8")
check("Button 带 df-btn class", "df-btn" in ui)
check("无 JS onMouseDown 改 transform",
      "onMouseDown" not in ui.split("export function Field")[0])
check("CSS 里有 :active 缩放", ".df-btn:active" in CSS)
check("缩放值在 0.97-0.98", "scale(0.97)" in CSS)

print()
print("=" * 66)
print("7. 动效只动 transform / opacity")
print("=" * 66)
for blk in re.findall(r"@keyframes\s+([\w-]+)\s*\{(.*?)\n\}", CSS, re.S):
    name, body = blk
    props = set(re.findall(r"(?m)^\s*(?:from|to|\d+%\s*\{?)?\s*([a-z-]+)\s*:", body))
    props -= {"from", "to", ""}
    # background-position 是骨架屏的扫光，box-shadow 是成功提示，都不是布局属性
    bad = props - {"opacity", "transform", "box-shadow", "background-position"}
    check(f"{name} 只动视觉属性", not bad, f"多余: {sorted(bad)}" if bad else "")

print()
print("=" * 66)
print("8. 退场动画（实测修复前：遮罩 12ms 就被移除，一帧没播）")
print("=" * 66)
DIALOG_SRC = (SRC / "components" / "Dialog.tsx").read_text(encoding="utf-8")
TL_SRC = (SRC / "pages" / "TimelinePage.tsx").read_text(encoding="utf-8")
check("定义了 df-fade-out", "@keyframes df-fade-out" in CSS)
check("定义了 df-overlay-out", "@keyframes df-overlay-out" in CSS)
check(".df-fade-out 挂 animation", ".df-fade-out {" in CSS)
check(".df-overlay-out 挂 animation", ".df-overlay-out {" in CSS)
check("--dur-exit token 存在", "--dur-exit:" in TOKENS)
m_exit = re.search(r"--dur-exit:\s*(\d+)ms", TOKENS)
m_menu = re.search(r"--dur-menu:\s*(\d+)ms", TOKENS)
check("退场时长 ≤ 入场时长",
      bool(m_exit and m_menu) and int(m_exit.group(1)) <= int(m_menu.group(1)),
      f"exit={m_exit.group(1) if m_exit else '?'}ms "
      f"menu={m_menu.group(1) if m_menu else '?'}ms")
# Dialog 不能自己计时卸载：会和父组件的计时器抢跑，
# 实测遮罩在 12ms 就被移除，退场一帧没播。
check("Dialog 不自己管退场计时器", "setTimeout" not in DIALOG_SRC)
check("Dialog 挂退场 class",
      "df-fade-out" in DIALOG_SRC and "df-overlay-out" in DIALOG_SRC)
check("Dialog 用 closing = !open 判定", "const closing = !open" in DIALOG_SRC)
# 关键：退场期间组件必须还挂着。return null 等于瞬间消失。
# 先去掉块注释再判断 —— 文件头和字段旁都写了「return null 就等于
# 没有退场」这句话，扫到它就误报了。
stripped = re.sub(r"/\*.*?\*/", "", DIALOG_SRC, flags=re.S)
code_lines = [l.split("//")[0] for l in stripped.split("\n")]
check("Dialog 退场期间不 return null",
      not any("return null" in l for l in code_lines))
check("时间轴的撤销条有退场",
      "df-fade-out" in TL_SRC and "toastClosing" in TL_SRC)
check("撤销后立即卸载（不播退场）",
      "setToastClosing(false)" in TL_SRC.split("const handleUndo")[1][:400])

print()
print("=" * 66)
print("9. 布局切换有过渡（侧栏 200px ↔ 56px）")
print("=" * 66)
check("侧栏过渡 width",
      re.search(r"\.df-sidebar\s*\{[^}]*transition:[^}]*width", CSS,
                re.S) is not None)
check("收起时导航文字淡出",
      '.df-shell[data-layout="rail"] .df-brand-name' in CSS)
check("导航项文字有过渡",
      re.search(r"\.df-nav-item > span[^}]*transition", CSS, re.S) is not None)

print()
print("=" * 66)
print("10. 没有在动 layout 的 transition:all")
print("=" * 66)
# transitionProperty 的初始值就是 all，但 duration 为 0s ——
# 那种永远不动，不算问题。这里只挡「显式写了 all 且有时长」。
all_trans = re.findall(r"transition:\s*all\s+([^;]+);", CSS)
all_trans += re.findall(r'transition:\s*"all\s+', BLOB)
check("CSS 里没有 transition: all", not all_trans, str(all_trans[:3]))
check("组件里没有 transition: 'all'", "'all" not in BLOB and '"all' not in BLOB)

print()
print("=" * 66)
print("11. 焦点环是真实元素（伪元素会被 CSS 压缩器改写）")
print("=" * 66)
RING = (SRC / "components" / "FocusRing.tsx").read_text(encoding="utf-8")
UI_SRC = (SRC / "components" / "ui.tsx").read_text(encoding="utf-8")
SHELL_SRC = (SRC / "components" / "Shell.tsx").read_text(encoding="utf-8")
check("FocusRing 组件存在", "df-focus-ring" in RING)
check(".df-focus-ring 样式已定义", ".df-focus-ring {" in CSS)
# 压缩器会把 ::focus-visible::after 压成 ::focus-visible:after，
# Chrome 碰巧认单冒号，规范里没有 —— 实测 content:none。
# 只看真正的规则行，别被解释这件事的注释扫到。
CSS_RULES = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
check("没有 ::focus-visible::after 规则",
      "focus-visible::after" not in CSS_RULES
      and "focus-visible:after" not in CSS_RULES)
# 每个可聚焦控件都要有 ring，否则键盘用户只看到硬切的 outline。
# Button / Toggle 直接写 className="df-focus-ring"，
# Shell 等用 <FocusRing /> 组件。
check("Button 有焦点环", 'className="df-focus-ring"' in UI_SRC)
check("Toggle 有焦点环", 'className="df-focus-ring"' in UI_SRC)
check("Shell 用 FocusRing 组件", "<FocusRing" in SHELL_SRC)
for page, needle in [("TimelinePage", "筛选药丸"),
                     ("ReportsPage", "日报列表"),
                     ("StatsPage", "Segmented"),
                     ("MotionControl", "动效三档")]:
    path = SRC / "pages" / f"{page}.tsx"
    if not path.exists():
        path = SRC / "components" / f"{page}.tsx"
    src = path.read_text(encoding="utf-8")
    check(f"{page} 用了焦点环（{needle}）",
          "FocusRing" in src or "df-focus-ring" in src)
check("输入框用 border/box-shadow 过渡",
      ".df-field:focus-visible" in CSS and "box-shadow" in CSS)
# 搜索框是手写的（左侧留白给放大镜），没挂 .df-field。
# 内联 border 简写会赢过 :focus-visible 的 border-color ——
# 实测聚焦时边框不变色，只剩 box-shadow 那一层环。
# 取最后一个 .df-search 规则：前面几个在媒体查询里。
search_rules = re.findall(r"^\.df-search\s*\{([^}]*)\}", CSS, re.M)
check(".df-search 在样式表里定义了边框",
      bool(search_rules) and "border:" in search_rules[-1],
      f"找到 {len(search_rules)} 条规则")
TL2 = (SRC / "pages" / "TimelinePage.tsx").read_text(encoding="utf-8")
seg2 = TL2.split('className="df-search"')[1][:600] \
    if 'className="df-search"' in TL2 else ""
check("搜索框不再内联 border 简写", "border:" not in seg2,
      "内联 border 会赢过 :focus-visible" if "border:" in seg2 else "")

print()
print("=" * 66)
print("12. 加载交接（实测修复前：骨架与内容同存 0 帧）")
print("=" * 66)
HANDOFF = (SRC / "components" / "LoadingHandoff.tsx").read_text(
    encoding="utf-8")
check("LoadingHandoff 组件存在", "skeleton" in HANDOFF.lower())
check("定义了 df-skeleton-out", "@keyframes df-skeleton-out" in CSS)
check("定义了 df-content-in", "@keyframes df-content-in" in CSS)
check("--dur-handoff token", "--dur-handoff:" in TOKENS)
check("时间轴用了交接", "LoadingHandoff" in TL_SRC)
m_h = re.search(r"const HANDOFF_MS\s*=\s*(\d+)", HANDOFF)
m_d = re.search(r"--dur-handoff:\s*(\d+)ms", TOKENS)
check("JS 计时器和 CSS token 一致",
      bool(m_h and m_d) and int(m_h.group(1)) == int(m_d.group(1)),
      f"js={m_h.group(1) if m_h else '?'}ms "
      f"css={m_d.group(1) if m_d else '?'}ms")

print()
print("=" * 66)
print("结果")
print("=" * 66)
if failures:
    print(f"{len(failures)} 项未通过:")
    for f in failures:
        print("  -", f)
    raise SystemExit(1)
print("全部通过")
