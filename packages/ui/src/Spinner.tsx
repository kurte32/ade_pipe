export function Spinner({ label = "Cargando" }: { label?: string }) {
  return (
    <div className="spinner" role="status" aria-live="polite">
      <span className="spinner-dot" aria-hidden="true" />
      <span>{label}…</span>
    </div>
  );
}
