import { ReactNode } from "react";

export type LineIconName =
  | "clock"
  | "file"
  | "chart"
  | "settings"
  | "sun"
  | "sparkles"
  | "record"
  | "mail"
  | "monitor"
  | "database"
  | "info";

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
};

export function LineIcon({
  name,
  size = 18,
}: {
  name: LineIconName;
  size?: number;
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
      style={{ display: "block", flexShrink: 0 }}
    >
      {ICONS[name]}
    </svg>
  );
}
