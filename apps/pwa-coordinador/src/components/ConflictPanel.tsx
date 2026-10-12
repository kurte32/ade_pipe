import { Alert, ESTATUS_LABELS, Icon } from "@pipeline/ui";

import type { Operacion } from "../db/schema";
import { getDb } from "../db/schema";
import { useSync } from "../sync/context";
import { discardOperation, retryOperation } from "../sync/engine";

const TIPO_LABEL: Record<Operacion["tipo"], string> = {
  contacto: "Contacto del dueño",
  visita: "Medidas del local",
  transicion: "Avance de estatus",
  foto: "Foto",
};

export function ConflictPanel({ ops }: { ops: Operacion[] }) {
  const sync = useSync();
  const relevant = ops.filter((o) => o.estado === "bloqueada" || o.estado === "error");
  if (relevant.length === 0) return null;
  return (
    <section className="card tone-attention" aria-labelledby="conflicto-h" data-testid="conflict-panel">
      <h2 id="conflicto-h">
        <Icon name="alert-triangle" size={18} /> Cambios que no se pudieron aplicar
      </h2>
      <p className="section-sub">Revisa el estado actual del sitio y decide qué hacer con cada cambio guardado en el teléfono.</p>
      {relevant.map((op) => (
        <div key={op.id} className="stack" style={{ borderTop: "1px solid var(--color-border)", paddingTop: "var(--space-3)", marginTop: "var(--space-3)" }}>
          <div>
            <strong>{TIPO_LABEL[op.tipo]}</strong>
            {op.tipo === "transicion" ? (
              <span className="muted"> → {ESTATUS_LABELS[(op.payload as { estatus_destino: string }).estatus_destino] ?? ""}</span>
            ) : null}
          </div>
          <Alert tone="error" role="none">
            <p>{op.error}</p>
            {op.faltantes?.length ? (
              <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                {op.faltantes.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            ) : null}
          </Alert>
          {op.conflict ? (
            <p className="small">
              El servidor tiene el sitio en <strong>{ESTATUS_LABELS[op.conflict.estatus] ?? op.conflict.estatus}</strong>
              {op.conflict.devuelto ? ` (devuelto por el administrador: ${op.conflict.devolucion_comentario ?? ""})` : ""}.
            </p>
          ) : null}
          <div className="actions">
            <button
              type="button"
              className="secondary"
              onClick={async () => {
                await retryOperation(getDb(), op.id);
                void sync.syncNow();
              }}
              data-testid={`retry-${op.id}`}
            >
              <Icon name="refresh" size={16} /> Reintentar con el estado actual
            </button>
            <button type="button" className="danger" onClick={() => void discardOperation(getDb(), op.id)} data-testid={`discard-${op.id}`}>
              <Icon name="trash" size={16} /> Descartar cambio local
            </button>
          </div>
        </div>
      ))}
    </section>
  );
}
