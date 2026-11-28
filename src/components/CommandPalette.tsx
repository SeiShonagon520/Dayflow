/*
 * 全局命令面板（Ctrl+K）
 *
 * 借鉴 shadcn/ui Command + beUI Command Palette 的键盘优先结构，
 * 复用本地 Dialog 原语（保留 .df-shell inert、Esc、焦点归还与 useExit），
 * 零第三方依赖、纯 CSS Token 换皮、无毛玻璃开销。
 */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Dialog } from "@/components/Dialog";
import { LineIcon, LineIconName } from "@/components/LineIcon";

export interface CommandAction {
  id: string;
  group: string;
  label: string;
  hint?: string;
  shortcut?: string;
  keywords?: string;
  icon: LineIconName;
  disabled?: boolean;
  onSelect: () => void;
}

export function CommandPalette({
  open,
  onClose,
  onExited,
  actions,
}: {
  open: boolean;
  onClose: () => void;
  onExited: () => void;
  actions: CommandAction[];
}) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const keyboardSelection = useRef(false);
  const listId = useId();
  const titleId = useId();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const enabled = actions.filter((a) => !a.disabled);
    if (!q) return enabled;
    return enabled.filter((a) => {
      const hay = `${a.label} ${a.hint ?? ""} ${a.group} ${a.keywords ?? ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [actions, query]);

  const safeIndex = filtered.length > 0 ? Math.min(activeIndex, filtered.length - 1) : -1;

  const grouped = useMemo(() => {
    const map = new Map<string, { item: CommandAction; flatIndex: number }[]>();
    filtered.forEach((item, flatIndex) => {
      const bucket = map.get(item.group) ?? [];
      bucket.push({ item, flatIndex });
      map.set(item.group, bucket);
    });
    return [...map.entries()];
  }, [filtered]);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [open]);

  const execute = (action: CommandAction | undefined) => {
    if (!action || action.disabled) return;
    onClose();
    action.onSelect();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (filtered.length === 0) return;
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) keyboardSelection.current = true;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % filtered.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((prev) => (prev - 1 + filtered.length) % filtered.length);
    } else if (e.key === "Home") {
      e.preventDefault();
      setActiveIndex(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActiveIndex(filtered.length - 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      execute(filtered[safeIndex]);
    }
  };

  const activeId = safeIndex >= 0 ? `${listId}-opt-${filtered[safeIndex].id}` : undefined;
  useEffect(() => {
    if (!keyboardSelection.current || !activeId) return;
    keyboardSelection.current = false;
    document.getElementById(activeId)?.scrollIntoView?.({ block: "nearest" });
  }, [activeId]);

  return (
    <Dialog open={open} onClose={onClose} onExited={onExited} labelledBy={titleId} size="lg" flush>
      <div className="df-cmd" onKeyDown={onKeyDown}>
        <h2 id={titleId} className="u-sr-only">命令面板</h2>
        <div className="df-cmd-search">
          <span className="df-cmd-search-icon" aria-hidden="true">
            <LineIcon name="search" size={16} />
          </span>
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={activeId}
            aria-label="输入命令或页面名称"
            placeholder="输入命令、页面或操作…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            className="df-cmd-input"
          />
          {query && (
            <button
              type="button"
              className="df-icon-btn"
              aria-label="清除输入"
              onClick={() => {
                setQuery("");
                setActiveIndex(0);
                inputRef.current?.focus();
              }}
            >
              <LineIcon name="x" size={13} />
            </button>
          )}
          <kbd className="df-kbd">Esc</kbd>
        </div>

        <div id={listId} role="listbox" aria-label="可用命令" className="df-cmd-list">
          {grouped.length === 0 ? (
            <div className="df-cmd-empty">
              <LineIcon name="search" size={20} />
              <span>没有匹配的命令</span>
            </div>
          ) : (
            grouped.map(([group, entries]) => (
              <div key={group} className="df-cmd-group" role="group" aria-label={group}>
                <div className="df-cmd-group-label">{group}</div>
                {entries.map(({ item, flatIndex }) => {
                  const selected = flatIndex === safeIndex;
                  return (
                    <button
                      key={item.id}
                      id={`${listId}-opt-${item.id}`}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      tabIndex={-1}
                      data-active={selected ? "true" : undefined}
                      className="df-cmd-item"
                      onPointerMove={(event) => {
                        if (event.pointerType === "mouse") setActiveIndex(flatIndex);
                      }}
                      onClick={() => execute(item)}
                    >
                      <span className="df-cmd-item-icon" aria-hidden="true">
                        <LineIcon name={item.icon} size={15} />
                      </span>
                      <span className="df-cmd-item-main">
                        <span className="df-cmd-item-label">{item.label}</span>
                        {item.hint && <span className="df-cmd-item-hint">{item.hint}</span>}
                      </span>
                      {item.shortcut && <kbd className="df-kbd">{item.shortcut}</kbd>}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        <div className="df-cmd-foot" aria-hidden="true">
          <span><kbd className="df-kbd">↑↓</kbd> 选择</span>
          <span><kbd className="df-kbd">Enter</kbd> 执行</span>
          <span><kbd className="df-kbd">Esc</kbd> 关闭</span>
        </div>
      </div>
    </Dialog>
  );
}
