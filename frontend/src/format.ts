const dateTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Dhaka",
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** Formats a UTC ISO timestamp in Bangladesh time; missing values are shown explicitly. */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "unknown";
  return `${dateTime.format(new Date(iso))} BDT`;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

export function pct(part: number, whole: number): string {
  return whole ? `${Math.round((100 * part) / whole)}%` : "–";
}
