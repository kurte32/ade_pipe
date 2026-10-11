import { ESTATUS_LABELS, ESTATUS_ORDER } from "./EstatusBadge";

/** The four coordinator stages as a progress bar. Terminal statuses render nothing (the badge says it). */
export function StageIndicator({ estatus, compact }: { estatus: string; compact?: boolean }) {
  const idx = (ESTATUS_ORDER as readonly string[]).indexOf(estatus);
  if (idx < 0) return null;
  return (
    <ol className={`stages${compact ? " compact" : ""}`} aria-label={`Etapa ${idx + 1} de ${ESTATUS_ORDER.length}: ${ESTATUS_LABELS[estatus]}`}>
      {ESTATUS_ORDER.map((s, i) => (
        <li key={s} className={i < idx ? "done" : i === idx ? "current" : ""} aria-current={i === idx ? "step" : undefined}>
          <span className="bar" />
          <span className="lbl">{ESTATUS_LABELS[s]}</span>
        </li>
      ))}
    </ol>
  );
}
