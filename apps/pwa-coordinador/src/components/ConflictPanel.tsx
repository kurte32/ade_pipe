import { ESTATUS_LABELS } from "@pipeline/ui";

import type { Operacion } from "../db/schema";
import { discardOperation, retryOperation } from "../sync/engine";
import { getDb } from "../db/schema";
import { useSync } from "../sync/context";

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
    <section className="problem" aria-labelledby="conflicto-h" data-testid="conflict-panel">
      <h2 id="conflicto-h">Cambios que no se pudieron aplicar</h2>
      {relevant.map((op) => (
        <div key={op.id} className="card" style={{ color: "inherit" }}>
          <strong>{TIPO_LABEL[op.tipo]}</strong>
          {op.tipo === "transicion" ? (
            <span className="muted"> → {ESTATUS_LABELS[(op.payload as { estatus_destino: string }).estatus_destino] ?? ""}</span>
          ) : null}
          <p>{op.error}</p>
          {op.faltantes?.length ? (
            <ul>
              {op.faltantes.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          ) : null}
          {op.conflict ? (
            <p className="muted">
              El servidor tiene el sitio en <strong>{ESTATUS_LABELS[op.conflict.estatus] ?? op.conflict.estatus}</strong>
              {op.conflict.devuelto ? ` (devuelto por el administrador: ${op.conflict.devolucion_comentario ?? ""})` : ""}.
            </p>
          ) : null}
          <div className="row">
            <button
              type="button"
              className="secondary"
              onClick={async () => {
                await retryOperation(getDb(), op.id);
                void sync.syncNow();
              }}
              data-testid={`retry-${op.id}`}
            >
              Reintentar con el estado actual
            </button>
            <button type="button" className="danger" onClick={() => void discardOperation(getDb(), op.id)} data-testid={`discard-${op.id}`}>
              Descartar cambio local
            </button>
          </div>
        </div>
      ))}
    </section>
  );
}
