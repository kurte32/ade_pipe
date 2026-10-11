import { EstatusBadge, ESTATUS_LABELS, Spinner, formatMexicoCity } from "@pipeline/ui";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ConflictPanel } from "../components/ConflictPanel";
import { ContactoForm } from "../components/ContactoForm";
import { DocumentosSection } from "../components/DocumentosSection";
import { FotosSection } from "../components/FotosSection";
import { HistorialList } from "../components/HistorialList";
import { VisitaForm } from "../components/VisitaForm";
import { requiredDocTypes, useCatalogos } from "../lib/catalogos";
import { nextEstatus, type ContactoIn, type SitioDetail, type VisitaIn } from "../lib/types";
import { useCachedSitio, useOperaciones } from "../lib/useSitios";
import { useSync } from "../sync/context";
import { refreshSitio } from "../sync/engine";

/** Client-side mirror of backend/app/modules/transiciones/rules.py, used only for hints. */
function precheck(detail: SitioDetail, destino: string, requiredDocs: string[], pendingTipos: Set<string>): string[] {
  const missing: string[] = [];
  if (destino === "dueno_localizado" && !detail.contacto && !pendingTipos.has("contacto")) {
    missing.push("Captura el contacto del dueño (nombre y teléfono)");
  }
  if (destino === "primera_visita" && !detail.visita && !pendingTipos.has("visita")) {
    missing.push("Captura las medidas del local");
  }
  if (destino === "recepcion_documentos") {
    for (const t of requiredDocs) {
      const ok = detail.archivos.some((a) => a.tipo === "documento" && a.tipo_documento === t && a.vigente && a.estado === "publicado");
      if (!ok) missing.push(`Falta el documento: ${t}`);
    }
  }
  return missing;
}

export function SitioDetalle() {
  const { id } = useParams();
  const sitioId = Number(id);
  const cached = useCachedSitio(sitioId);
  const ops = useOperaciones(sitioId) ?? [];
  const sync = useSync();
  const catalogos = useCatalogos();
  const [comentarioDescarte, setComentarioDescarte] = useState("");
  const [showDescarte, setShowDescarte] = useState(false);
  const [refreshKey, setRefreshKey] = useState("0");
  const [flash, setFlash] = useState("");

  const requiredDocs = useMemo(() => requiredDocTypes(catalogos), [catalogos]);
  const pendingTipos = useMemo(() => new Set(ops.filter((o) => o.estado !== "bloqueada").map((o) => o.tipo)), [ops]);
  const pendingContacto = ops.find((o) => o.tipo === "contacto" && o.estado !== "bloqueada");
  const pendingVisita = ops.find((o) => o.tipo === "visita" && o.estado !== "bloqueada");
  const pendingTransicion = ops.find((o) => o.tipo === "transicion" && o.estado !== "bloqueada");

  if (cached === undefined) return <Spinner label="Cargando sitio" />;
  if (cached === null) {
    return (
      <main>
        <p>Este sitio no está en tu caché local. {sync.online ? "Sincroniza para actualizar." : "Conéctate para consultarlo."}</p>
        <Link to="/">Volver</Link>
      </main>
    );
  }
  const s = cached.detail;
  const siguiente = nextEstatus(s.estatus);
  const terminal = !siguiente && s.estatus !== "recepcion_documentos" ? true : false;
  const missing = siguiente ? precheck(s, siguiente, requiredDocs.map((t) => t.id), pendingTipos) : [];
  const docTypeNames = Object.fromEntries(catalogos.tipos_documento.map((t) => [t.id, t.nombre]));

  async function afterServerChange() {
    await refreshSitio(sync.deps, sitioId);
    setRefreshKey(String(Date.now()));
  }

  async function guardarContacto(c: ContactoIn) {
    await sync.enqueueOp(sitioId, "contacto", c);
    setFlash(sync.online ? "Contacto enviado." : "Contacto guardado; se enviará al recuperar señal.");
  }
  async function guardarVisita(v: VisitaIn) {
    await sync.enqueueOp(sitioId, "visita", v);
    setFlash(sync.online ? "Medidas enviadas." : "Medidas guardadas; se enviarán al recuperar señal.");
  }
  async function avanzar() {
    if (!siguiente) return;
    await sync.enqueueOp(sitioId, "transicion", { estatus_destino: siguiente, comentario: null });
    setFlash(sync.online ? "Avance enviado." : "Avance guardado; se confirmará al sincronizar.");
    setRefreshKey(String(Date.now()));
  }
  async function proponerDescarte() {
    if (comentarioDescarte.trim().length < 5) return;
    await sync.enqueueOp(sitioId, "transicion", { estatus_destino: "descartado", comentario: comentarioDescarte.trim() });
    setShowDescarte(false);
    setComentarioDescarte("");
    setFlash("Propuesta de descarte enviada al administrador.");
  }

  return (
    <main>
      <p>
        <Link to="/">← Mis sitios</Link>
      </p>
      <h1>{s.nombre}</h1>
      <div className="row">
        <EstatusBadge estatus={s.estatus} devuelto={s.devuelto} />
        {pendingTransicion ? <span className="pending" data-testid="pending-badge">pendiente de sincronizar</span> : null}
        {s.en_revision_admin ? <span className="muted">en revisión del administrador</span> : null}
      </div>
      <p className="muted">
        #{s.origen_id} · {s.region} · potencial {s.potencial} · campos {s.campos_capturados}/{s.campos_total} · origen {formatMexicoCity(s.fecha_origen_utc)}
      </p>
      <p className="muted">
        Coordenadas {s.lat}, {s.lon}
        {s.gps_texto ? ` · GPS ${s.gps_texto}` : ""}
      </p>
      {s.devuelto ? (
        <div className="problem" role="alert" data-testid="devuelto-banner">
          <strong>Devuelto por el administrador</strong>
          <p>
            Motivo: {s.devolucion_motivo ?? ""}. {s.devolucion_comentario ?? ""}
          </p>
        </div>
      ) : null}
      {flash ? (
        <p role="status" className="pending" data-testid="flash">
          {flash}
        </p>
      ) : null}
      <ConflictPanel ops={ops} />

      <section className="card" aria-labelledby="avance-h">
        <h2 id="avance-h">Estatus</h2>
        {siguiente ? (
          <>
            {missing.length ? (
              <ul className="muted" data-testid="precheck">
                {missing.map((m) => (
                  <li key={m}>{m.replace(/^Falta el documento: (\w+)$/, (_, t: string) => `Falta el documento: ${docTypeNames[t] ?? t}`)}</li>
                ))}
              </ul>
            ) : null}
            <button type="button" onClick={() => void avanzar()} disabled={missing.length > 0 || !!pendingTransicion} data-testid="avanzar">
              Avanzar a {ESTATUS_LABELS[siguiente]}
            </button>
          </>
        ) : terminal ? (
          <p className="muted">El sitio está en un estatus final.</p>
        ) : (
          <p className="muted">El sitio completó todas las etapas del coordinador.</p>
        )}
        {!terminal && !s.en_revision_admin ? (
          <div style={{ marginTop: 12 }}>
            {showDescarte ? (
              <div>
                <label htmlFor="descarte-comentario">Motivo del descarte</label>
                <textarea id="descarte-comentario" rows={2} value={comentarioDescarte} onChange={(e) => setComentarioDescarte(e.target.value)} />
                <div className="row" style={{ marginTop: 8 }}>
                  <button type="button" className="danger" onClick={() => void proponerDescarte()} disabled={comentarioDescarte.trim().length < 5}>
                    Enviar propuesta
                  </button>
                  <button type="button" className="secondary" onClick={() => setShowDescarte(false)}>
                    Cancelar
                  </button>
                </div>
              </div>
            ) : (
              <button type="button" className="secondary" onClick={() => setShowDescarte(true)}>
                Proponer descarte
              </button>
            )}
          </div>
        ) : null}
      </section>

      <section className="card" aria-labelledby="contacto-h">
        <h2 id="contacto-h">Contacto del dueño</h2>
        {pendingContacto ? <p className="pending">Hay un contacto pendiente de sincronizar.</p> : null}
        {s.contacto && !pendingContacto ? (
          <p className="muted">
            Capturado {formatMexicoCity(s.contacto.capturado_utc)}: {s.contacto.nombre}, {s.contacto.telefono}
          </p>
        ) : null}
        <ContactoForm
          key={`c-${cached.etag}-${pendingContacto?.id ?? ""}`}
          initial={(pendingContacto?.payload as ContactoIn | undefined) ?? s.contacto ?? null}
          onSubmit={guardarContacto}
          disabled={terminal}
        />
      </section>

      <section className="card" aria-labelledby="visita-h">
        <h2 id="visita-h">Medidas del local</h2>
        {pendingVisita ? <p className="pending">Hay medidas pendientes de sincronizar.</p> : null}
        <VisitaForm
          key={`v-${cached.etag}-${pendingVisita?.id ?? ""}`}
          initial={(pendingVisita?.payload as VisitaIn | undefined) ?? (s.visita as VisitaIn | null) ?? null}
          onSubmit={guardarVisita}
          disabled={terminal}
        />
      </section>

      <div className="card">
        <FotosSection sitioId={sitioId} publicadas={s.archivos.filter((a) => a.tipo === "foto" && a.vigente)} disabled={terminal} />
      </div>
      <div className="card">
        <DocumentosSection sitioId={sitioId} tipos={requiredDocs} archivos={s.archivos} onPublished={afterServerChange} disabled={terminal} />
      </div>
      <div className="card">
        <HistorialList sitioId={sitioId} refreshKey={`${refreshKey}-${cached.etag}`} />
      </div>
    </main>
  );
}
