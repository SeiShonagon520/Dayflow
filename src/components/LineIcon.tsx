import { ReactNode } from "react";

export type LineIconName =
  | "clock"
  | "file"
  | "chart"
  | "settings"
  | "sun"
  | "moon"
  | "sparkles"
  | "record"
  | "mail"
  | "monitor"
  | "database"
  | "info"
  | "play"
  | "pause"
  | "stop"
  | "check"
  | "x"
  | "chevron-left"
  | "chevron-right"
  | "chevron-down"
  | "search"
  | "edit"
  | "trash"
  | "alert"
  | "inbox"
  | "copy"
  | "clipboard"
  | "command"
  | "plus"
  | "minus"
  | "calendar"
  | "arrow-right"
  | "external-link";

const ICONS: Record<LineIconName, ReactNode> = {
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  file: (
    <>
      <path d="M6 3.75h8l4 4v12.5H6z" />
      <path d="M14 3.75v4h4M9 12h6M9 15.5h6" />
    </>
  ),
  chart: <path d="M4 19.5h16M5.5 17V11M10 17V6.5M14.5 17v-4M19 17V8.5" />,
  settings: (
    <>
      <path d="M9.7 3.8h4.6l.55 2.1a6.8 6.8 0 0 1 1.6.92l2.06-.7 2.3 4-1.52 1.55a7.2 7.2 0 0 1 0 1.86l1.52 1.55-2.3 4-2.06-.7a6.8 6.8 0 0 1-1.6.92l-.55 2.1H9.7l-.55-2.1a6.8 6.8 0 0 1-1.6-.92l-2.06.7-2.3-4 1.52-1.55a7.2 7.2 0 0 1 0-1.86L3.19 10.1l2.3-4 2.06.7a6.8 6.8 0 0 1 1.6-.92z" />
      <circle cx="12" cy="12.6" r="2.7" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2M12 19.5v2M4.7 4.7l1.4 1.4m11.8 11.8 1.4 1.4M2.5 12h2m15 0h2M4.7 19.3l1.4-1.4M17.9 6.1l1.4-1.4" />
    </>
  ),
  moon: (
    <path d="M19.2 14.6A7.5 7.5 0 0 1 9.4 4.8a7.5 7.5 0 1 0 9.8 9.8Z" />
  ),
  sparkles: (
    <>
      <path d="m12 3 1.55 5.45L19 10l-5.45 1.55L12 17l-1.55-5.45L5 10l5.45-1.55L12 3Z" />
      <path d="m19 15 .75 2.25L22 18l-2.25.75L19 21l-.75-2.25L16 18l2.25-.75L19 15Z" />
    </>
  ),
  record: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="3.25" fill="currentColor" stroke="none" />
    </>
  ),
  mail: (
    <>
      <rect x="3.5" y="5.25" width="17" height="13.5" rx="2" />
      <path d="m4.5 7 7.5 5.75L19.5 7" />
    </>
  ),
  monitor: (
    <>
      <rect x="3.25" y="4.25" width="17.5" height="12.5" rx="1.8" />
      <path d="M9 20h6m-3-3.25V20" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="5.5" rx="7.75" ry="2.75" />
      <path d="M4.25 5.5v13c0 1.5 3.47 2.75 7.75 2.75s7.75-1.25 7.75-2.75v-13M4.25 12c0 1.5 3.47 2.75 7.75 2.75s7.75-1.25 7.75-2.75" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 10.75v5m0-8.5h.01" />
    </>
  ),
  play: (
    <path d="M7.5 5.75 18 12l-10.5 6.25V5.75Z" fill="currentColor" strokeLinejoin="round" />
  ),
  pause: (
    <>
      <rect x="6.5" y="5.5" width="3.5" height="13" rx="1" fill="currentColor" stroke="none" />
      <rect x="14" y="5.5" width="3.5" height="13" rx="1" fill="currentColor" stroke="none" />
    </>
  ),
  stop: (
    <rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" stroke="none" />
  ),
  check: <path d="m5.5 12.5 4.2 4.2L18.5 7.8" />,
  x: <path d="M6.5 6.5 17.5 17.5M17.5 6.5 6.5 17.5" />,
  "chevron-left": <path d="m14.5 6.5-5.5 5.5 5.5 5.5" />,
  "chevron-right": <path d="m9.5 6.5 5.5 5.5-5.5 5.5" />,
  "chevron-down": <path d="m6.5 9.5 5.5 5.5 5.5-5.5" />,
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </>
  ),
  edit: (
    <>
      <path d="M15.2 4.8a2.1 2.1 0 0 1 3 3L8.8 17.2 5 18.5l1.3-3.8 8.9-9.9Z" />
    </>
  ),
  trash: (
    <>
      <path d="M4.5 7h15M9.5 7V5a1.5 1.5 0 0 1 1.5-1.5h2A1.5 1.5 0 0 1 14.5 5v2" />
      <path d="M6.8 7l.8 11.5a1.8 1.8 0 0 0 1.8 1.7h5.2a1.8 1.8 0 0 0 1.8-1.7L17.2 7" />
    </>
  ),
  alert: (
    <>
      <path d="M12 4 3.6 18.8a1.2 1.2 0 0 0 1.04 1.8h14.72a1.2 1.2 0 0 0 1.04-1.8L12 4Z" />
      <path d="M12 9.5v4.5m0 3.2h.01" />
    </>
  ),
  inbox: (
    <>
      <path d="M4 13.5 6.4 5.5h11.2l2.4 8v5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5v-5Z" />
      <path d="M4 13.5h4.5l1.4 2.2h4.2l1.4-2.2H20" />
    </>
  ),
  copy: (
    <>
      <rect x="8.5" y="8.5" width="11" height="11" rx="2" />
      <path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5" />
    </>
  ),
  clipboard: (
    <>
      <rect x="5" y="4.5" width="14" height="16" rx="2" />
      <path d="M9 4.5V3.5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1M8.5 10.5h7M8.5 14.5h5" />
    </>
  ),
  command: (
    <path d="M18 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3 3 3 0 0 0 3-3 3 3 0 0 0-3-3H6a3 3 0 0 0-3 3 3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3 3 3 0 0 0 3 3h12a3 3 0 0 0 3-3 3 3 0 0 0-3-3Z" />
  ),
  plus: <path d="M12 5.5v13M5.5 12h13" />,
  minus: <path d="M5.5 12h13" />,
  calendar: (
    <>
      <rect x="3.75" y="5" width="16.5" height="15" rx="2" />
      <path d="M8 3.25v3M16 3.25v3M3.75 9.5h16.5" />
    </>
  ),
  "arrow-right": <path d="M5.5 12h13M13 6.5 18.5 12 13 17.5" />,
  "external-link": (
    <>
      <path d="M14.5 4.5h5v5M19.5 4.5 11 13" />
      <path d="M18 13.5v4a2 2 0 0 1-2 2H6.5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" />
    </>
  ),
};

export function LineIcon({
  name,
  size = 18,
  className,
}: {
  name: LineIconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={{ display: "block", flexShrink: 0 }}
    >
      {ICONS[name]}
    </svg>
  );
}
