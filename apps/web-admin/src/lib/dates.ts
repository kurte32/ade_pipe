/**
 * Convert a `datetime-local` input value (interpreted in the given IANA zone, default
 * America/Mexico_City) to a UTC ISO string for the API. Mexico City has no DST since 2022,
 * but the conversion is done through Intl so it stays correct if that ever changes.
 */
export function localToUtcIso(local: string, timeZone = "America/Mexico_City"): string | undefined {
  if (!local) return undefined;
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(local);
  if (!m) return undefined;
  const [, y, mo, d, h, mi, s] = m;
  const asUtc = Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s ?? "0"));
  const offsetMs = zoneOffsetMs(new Date(asUtc), timeZone);
  return new Date(asUtc - offsetMs).toISOString();
}

/** Offset (ms) of `timeZone` relative to UTC at the given instant. */
export function zoneOffsetMs(at: Date, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(at);
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? "0");
  const zoned = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
  return zoned - at.getTime();
}
