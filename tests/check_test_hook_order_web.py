"""Hook 顺序静态检查。

React 的 hook 必须在所有 early return 之前调用。放在后面时，
加载中的那一帧会少一个 hook，React 抛
"Rendered more hooks than during the previous render"，
整页白掉 —— 而且只在慢网络下出现，正常速度测不出来。

这个 bug 我在设置页和统计页各写了一次，都是改响应式时
顺手把 useIsPhone() 挪到 return 后面才引入的。

只检查组件函数体：模块级的普通工具函数里出现 return 是合法的，
把 useMQ 之类的自定义 hook 也算进来。
"""
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SRC = Path(__file__).resolve().parent.parent / "src"
FILES = sorted(SRC.glob("pages/*.tsx")) + sorted(SRC.glob("components/*.tsx"))

HOOK = re.compile(r"\buse[A-Z]\w*\s*\(")
COMPONENT = re.compile(
    r"^(export\s+)?(default\s+)?function\s+([A-Z]\w*)|"
    r"^export\s+const\s+([A-Z]\w*)\s*=\s*forwardRef")

failures = []
checked = 0

for f in FILES:
    lines = f.read_text(encoding="utf-8").split("\n")
    i = 0
    while i < len(lines):
        m = COMPONENT.match(lines[i])
        if not m:
            i += 1
            continue

        # 从组件声明往下找函数体结束（缩进回到顶格）
        start = i
        depth = 0
        body_end = len(lines)
        for j in range(i, len(lines)):
            depth += lines[j].count("{") - lines[j].count("}")
            if depth == 0 and j > i:
                body_end = j
                break
        body = lines[start + 1:body_end]

        first_hook = None
        first_early = None
        paren_depth = 0
        for k, line in enumerate(body, start + 2):
            st = line.strip()
            if first_hook is None and HOOK.search(st) and \
               not st.startswith("import"):
                first_hook = k
            if first_early is None:
                # useState 的惰性初始化里也有 return ——
                # 那是初始化函数的返回值，不是组件体的提前退出。
                if paren_depth > 0:
                    paren_depth += line.count("(") - line.count(")")
                    continue
                paren_depth = line.count("(") - line.count(")")
                # if (...) { 后紧跟 return，或条件 return
                if re.match(r"^if\s*\(.*\)\s*\{?\s*$", st) and \
                   any("return" in body[n] for n in
                       (k - start, k - start + 1, k - start + 2)
                       if 0 <= n - start < len(body)):
                    first_early = k
                elif st.startswith("return ") or st == "return (":
                    first_early = k

        if first_hook and first_early and first_hook > first_early:
            name = m.group(3) or m.group(4)
            failures.append((f, name, first_early, first_hook))
            checked += 1
        i = body_end + 1

print("=" * 68)
print("Hook 顺序检查（hook 必须在 early return 之前）")
print("=" * 68)
if failures:
    for f, name, early, hook in failures:
        print(f"  ✗ {f.relative_to(SRC)} :: {name}")
        print(f"      early return 在第 {early} 行，"
              f"hook 在第 {hook} 行 —— 慢网络下会崩")
    raise SystemExit(1)

print("  ✓ 未发现问题")
