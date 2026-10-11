import { Field } from "@pipeline/ui";
import { useRef, useState } from "react";

import { asNumber, type VisitaIn } from "../lib/types";

type Errors = Partial<Record<"frente" | "fondo" | "area" | "fecha", string>>;

export function VisitaForm({
  initial,
  onSubmit,
  onCancel,
  disabled,
}: {
  initial: Partial<VisitaIn> | null;
  onSubmit: (v: VisitaIn) => Promise<void>;
  onCancel?: () => void;
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
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  const f = asNumber(frente);
  const d = asNumber(fondo);
  const areaCalculada = f && d && f > 0 && d > 0 ? Math.round(f * d * 100) / 100 : null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const a = asNumber(area);
    const next: Errors = {};
    if (f === null || f <= 0) next.frente = "Escribe el frente en metros, mayor que cero.";
    if (d === null || d <= 0) next.fondo = "Escribe el fondo en metros, mayor que cero.";
    if (area && (a === null || a <= 0)) next.area = "El área debe ser un número mayor que cero.";
    if (!fecha || Number.isNaN(new Date(fecha).getTime())) next.fecha = "Indica la fecha de la visita.";
    setErrors(next);
    const first = (Object.keys(next) as (keyof Errors)[])[0];
    if (first) return formRef.current?.querySelector<HTMLElement>(`#v-${first}`)?.focus();
    setSaving(true);
    try {
      await onSubmit({
        frente_m: f!,
        fondo_m: d!,
        area_m2: a ?? f! * d!,
        notas: notas.trim() || null,
        fecha_visita_utc: new Date(fecha).toISOString(),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form ref={formRef} onSubmit={(e) => void submit(e)} aria-label="Medidas del local" noValidate>
      <div className="form-grid cols-2">
        <Field id="v-frente" label="Frente (m)" error={errors.frente}>
          <input type="number" inputMode="decimal" step="0.01" min="0.01" value={frente} onChange={(e) => setFrente(e.target.value)} required disabled={disabled} />
        </Field>
        <Field id="v-fondo" label="Fondo (m)" error={errors.fondo}>
          <input type="number" inputMode="decimal" step="0.01" min="0.01" value={fondo} onChange={(e) => setFondo(e.target.value)} required disabled={disabled} />
        </Field>
      </div>
      <Field
        id="v-area"
        label="Área (m², opcional; se calcula si se omite)"
        hint={areaCalculada && !area ? `Se guardará ${areaCalculada} m² (frente × fondo).` : "Déjala vacía para usar frente × fondo."}
        error={errors.area}
      >
        <input type="number" inputMode="decimal" step="0.01" min="0.01" value={area} onChange={(e) => setArea(e.target.value)} disabled={disabled} placeholder={areaCalculada ? String(areaCalculada) : ""} />
      </Field>
      <Field id="v-fecha" label="Fecha de la visita" error={errors.fecha}>
        <input type="datetime-local" value={fecha} onChange={(e) => setFecha(e.target.value)} disabled={disabled} />
      </Field>
      <Field id="v-notas" label="Notas (opcional)">
        <textarea value={notas} onChange={(e) => setNotas(e.target.value)} rows={2} maxLength={1000} disabled={disabled} />
      </Field>
      <div className="actions">
        <button type="submit" disabled={saving || disabled} data-testid="guardar-visita">
          {saving ? "Guardando…" : "Guardar medidas"}
        </button>
        {onCancel ? (
          <button type="button" className="ghost" onClick={onCancel} disabled={saving}>
            Cancelar
          </button>
        ) : null}
      </div>
    </form>
  );
}
