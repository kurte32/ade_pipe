import { useState } from "react";

import { asNumber, type VisitaIn } from "../lib/types";

export function VisitaForm({
  initial,
  onSubmit,
  disabled,
}: {
  initial: Partial<VisitaIn> | null;
  onSubmit: (v: VisitaIn) => Promise<void>;
  disabled?: boolean;
}) {
  const [frente, setFrente] = useState(initial?.frente_m != null ? String(initial.frente_m) : "");
  const [fondo, setFondo] = useState(initial?.fondo_m != null ? String(initial.fondo_m) : "");
  const [area, setArea] = useState(initial?.area_m2 != null ? String(initial.area_m2) : "");
  const [notas, setNotas] = useState(initial?.notas ?? "");
  const [fecha, setFecha] = useState(() => {
    const d = initial?.fecha_visita_utc ? new Date(initial.fecha_visita_utc + (initial.fecha_visita_utc.endsWith("Z") ? "" : "Z")) : new Date();
    return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const f = asNumber(frente);
    const d = asNumber(fondo);
    const a = asNumber(area);
    if (f === null || f <= 0) return setError("El frente debe ser un número mayor que cero");
    if (d === null || d <= 0) return setError("El fondo debe ser un número mayor que cero");
    if (area && (a === null || a <= 0)) return setError("El área debe ser un número mayor que cero");
    setError("");
    setSaving(true);
    try {
      await onSubmit({
        frente_m: f,
        fondo_m: d,
        area_m2: a ?? (f * d),
        notas: notas.trim() || null,
        fecha_visita_utc: new Date(fecha).toISOString(),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} aria-label="Medidas del local">
      <label htmlFor="v-frente">Frente (m)</label>
      <input id="v-frente" type="number" inputMode="decimal" step="0.01" min="0.01" value={frente} onChange={(e) => setFrente(e.target.value)} required disabled={disabled} />
      <label htmlFor="v-fondo">Fondo (m)</label>
      <input id="v-fondo" type="number" inputMode="decimal" step="0.01" min="0.01" value={fondo} onChange={(e) => setFondo(e.target.value)} required disabled={disabled} />
      <label htmlFor="v-area">Área (m², opcional; se calcula si se omite)</label>
      <input id="v-area" type="number" inputMode="decimal" step="0.01" min="0.01" value={area} onChange={(e) => setArea(e.target.value)} disabled={disabled} />
      <label htmlFor="v-fecha">Fecha de la visita</label>
      <input id="v-fecha" type="datetime-local" value={fecha} onChange={(e) => setFecha(e.target.value)} disabled={disabled} />
      <label htmlFor="v-notas">Notas (opcional)</label>
      <textarea id="v-notas" value={notas} onChange={(e) => setNotas(e.target.value)} rows={2} maxLength={1000} disabled={disabled} />
      {error ? <p role="alert" className="problem">{error}</p> : null}
      <div className="row" style={{ marginTop: 12 }}>
        <button type="submit" disabled={saving || disabled} data-testid="guardar-visita">
          {saving ? "Guardando…" : "Guardar medidas"}
        </button>
      </div>
    </form>
  );
}
