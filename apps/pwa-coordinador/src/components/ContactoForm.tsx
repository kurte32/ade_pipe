import { useState } from "react";

import type { ContactoIn } from "../lib/types";

export function ContactoForm({
  initial,
  onSubmit,
  disabled,
}: {
  initial: Partial<ContactoIn> | null;
  onSubmit: (c: ContactoIn) => Promise<void>;
  disabled?: boolean;
}) {
  const [nombre, setNombre] = useState(initial?.nombre ?? "");
  const [telefono, setTelefono] = useState(initial?.telefono ?? "");
  const [correo, setCorreo] = useState(initial?.correo ?? "");
  const [notas, setNotas] = useState(initial?.notas ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const digits = telefono.replace(/[\s\-()+]/g, "");
    if (!nombre.trim()) return setError("El nombre es obligatorio");
    if (!/^\d{10,15}$/.test(digits)) return setError("El teléfono debe tener entre 10 y 15 dígitos");
    if (correo.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo.trim())) return setError("Correo no válido");
    setError("");
    setSaving(true);
    try {
      await onSubmit({ nombre: nombre.trim(), telefono: digits, correo: correo.trim() || null, notas: notas.trim() || null });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} aria-label="Contacto del dueño">
      <label htmlFor="c-nombre">Nombre del dueño</label>
      <input id="c-nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} required maxLength={200} disabled={disabled} />
      <label htmlFor="c-telefono">Teléfono</label>
      <input id="c-telefono" type="tel" inputMode="tel" value={telefono} onChange={(e) => setTelefono(e.target.value)} required disabled={disabled} />
      <label htmlFor="c-correo">Correo (opcional)</label>
      <input id="c-correo" type="email" value={correo} onChange={(e) => setCorreo(e.target.value)} disabled={disabled} />
      <label htmlFor="c-notas">Notas (opcional)</label>
      <textarea id="c-notas" value={notas} onChange={(e) => setNotas(e.target.value)} rows={2} maxLength={1000} disabled={disabled} />
      {error ? <p role="alert" className="problem">{error}</p> : null}
      <div className="row" style={{ marginTop: 12 }}>
        <button type="submit" disabled={saving || disabled} data-testid="guardar-contacto">
          {saving ? "Guardando…" : "Guardar contacto"}
        </button>
      </div>
    </form>
  );
}
