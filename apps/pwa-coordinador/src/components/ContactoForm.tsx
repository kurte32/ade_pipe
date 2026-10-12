import { Field } from "@pipeline/ui";
import { useRef, useState } from "react";

import type { ContactoIn } from "../lib/types";

type Errors = Partial<Record<"nombre" | "telefono" | "correo", string>>;

export function ContactoForm({
  initial,
  onSubmit,
  onCancel,
  disabled,
}: {
  initial: Partial<ContactoIn> | null;
  onSubmit: (c: ContactoIn) => Promise<void>;
  onCancel?: () => void;
  disabled?: boolean;
}) {
  const [nombre, setNombre] = useState(initial?.nombre ?? "");
  const [telefono, setTelefono] = useState(initial?.telefono ?? "");
  const [correo, setCorreo] = useState(initial?.correo ?? "");
  const [notas, setNotas] = useState(initial?.notas ?? "");
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);

  function focusFirstError(e: Errors) {
    const first = (Object.keys(e) as (keyof Errors)[])[0];
    if (first) formRef.current?.querySelector<HTMLElement>(`#c-${first}`)?.focus();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const digits = telefono.replace(/[\s\-()+]/g, "");
    const next: Errors = {};
    if (!nombre.trim()) next.nombre = "Escribe el nombre del dueño.";
    if (!/^\d{10,15}$/.test(digits)) next.telefono = "El teléfono debe tener entre 10 y 15 dígitos.";
    if (correo.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo.trim())) next.correo = "Escribe un correo válido, por ejemplo nombre@dominio.com.";
    setErrors(next);
    if (Object.keys(next).length) return focusFirstError(next);
    setSaving(true);
    try {
      await onSubmit({ nombre: nombre.trim(), telefono: digits, correo: correo.trim() || null, notas: notas.trim() || null });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form ref={formRef} onSubmit={(e) => void submit(e)} aria-label="Contacto del dueño" noValidate>
      <Field id="c-nombre" label="Nombre del dueño" error={errors.nombre}>
        <input value={nombre} onChange={(e) => setNombre(e.target.value)} required maxLength={200} disabled={disabled} autoComplete="off" />
      </Field>
      <Field id="c-telefono" label="Teléfono" hint="10 a 15 dígitos, con lada." error={errors.telefono}>
        <input type="tel" inputMode="tel" value={telefono} onChange={(e) => setTelefono(e.target.value)} required disabled={disabled} autoComplete="off" />
      </Field>
      <Field id="c-correo" label="Correo (opcional)" error={errors.correo}>
        <input type="email" inputMode="email" value={correo} onChange={(e) => setCorreo(e.target.value)} disabled={disabled} autoComplete="off" />
      </Field>
      <Field id="c-notas" label="Notas (opcional)">
        <textarea value={notas} onChange={(e) => setNotas(e.target.value)} rows={2} maxLength={1000} disabled={disabled} />
      </Field>
      <div className="actions">
        <button type="submit" disabled={saving || disabled} data-testid="guardar-contacto">
          {saving ? "Guardando…" : "Guardar contacto"}
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
