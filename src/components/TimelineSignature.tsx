export function TimelineSignature() {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width="42"
      height="12"
      viewBox="0 0 42 12"
      style={{ display: "block", flexShrink: 0 }}
    >
      <path
        d="M2 6h38"
        fill="none"
        stroke="var(--timeline-track)"
        strokeWidth="1.25"
        strokeLinecap="round"
      />
      <circle cx="8" cy="6" r="2.3" fill="var(--cat-work)" stroke="var(--bg-surface)" strokeWidth="1" />
      <circle cx="21" cy="6" r="2.3" fill="var(--cat-study)" stroke="var(--bg-surface)" strokeWidth="1" />
      <circle cx="34" cy="6" r="2.3" fill="var(--cat-meeting)" stroke="var(--bg-surface)" strokeWidth="1" />
    </svg>
  );
}
