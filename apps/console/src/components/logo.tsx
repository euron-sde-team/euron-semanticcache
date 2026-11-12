/** Two overlapping circles: two different questions that mean the same thing. */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="8" fill="rgb(var(--accent))" />
      <circle cx="13" cy="16" r="7.2" fill="#fff" fillOpacity=".92" />
      <circle cx="19.5" cy="16" r="7.2" fill="#06312c" fillOpacity=".55" />
    </svg>
  );
}
