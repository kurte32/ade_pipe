const fmt = new Intl.DateTimeFormat("es-MX", {
  timeZone: "America/Mexico_City",
  dateStyle: "medium",
  timeStyle: "short",
});

/** API timestamps are naive UTC ("2026-10-10T18:25:41.516"). Render in Mexico City time (RNF-06). */
export function formatMexicoCity(utc: string | null | undefined): string {
  if (!utc) return "";
  const iso = /Z$|[+-]\d\d:\d\d$/.test(utc) ? utc : `${utc}Z`;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? utc : fmt.format(d);
}
