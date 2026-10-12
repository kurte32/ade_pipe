import { Alert, EstatusBadge, ESTATUS_LABELS, Icon, PageHeader, Spinner, StageIndicator, formatMexicoCity, potencialLabel, usePageTitle } from "@pipeline/ui";
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

interface Requisito {
  key: string;
  label: string;
  done: boolean;
  href: string;
}

/** Client-side mirror of backend/app/modules/transiciones/rules.py, used only for hints. */
function requisitos(detail: SitioDetail, destino: string, requiredDocs: { id: string; nombre: string }[], pendingTipos: Set<string>): Requisito[] {
  if (destino === "dueno_localizado") {
    return [{ key: "contacto", label: "Contacto del dueño (nombre y teléfono)", done: !!detail.contacto || pendingTipos.has("contacto"), href: "#contacto" }];
  }
  if (destino === "primera_visita") {
    return [{ key: "visita", label: "Medidas del local", done: !!detail.visita || pendingTipos.has("visita"), href: "#visita" }];
  }
  if (destino === "recepcion_documentos") {
    return requiredDocs.map((t) => ({
      key: `doc-${t.id}`,
      label: `Documento: ${t.nombre}`,
      done: detail.archivos.some((a) => a.tipo === "documento" && a.tipo_documento === t.id && a.vigente && a.estado === "publicado"),
      href: "#documentos",
    }));
  }
  return [];
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
  const [editContacto, setEditContacto] = useState(false);
  const [editVisita, setEditVisita] = useState(false);
  usePageTitle(cached?.detail.nombre ?? "Sitio");

  const requiredDocs = useMemo(() => requiredDocTypes(catalogos), [catalogos]);
  const motivos = useMemo(() => Object.fromEntries(catalogos.motivos_devolucion.map((m) => [m.codigo, m.nombre])), [catalogos]);
  const pendingTipos = useMemo(() => new Set(ops.filter((o) => o.estado !== "bloqueada").map((o) => o.tipo)), [ops]);
  // The newest queued capture is the one the user will see sent (several edits may be queued).
  const latest = (tipo: string) => [...ops].reverse().find((o) => o.tipo === tipo && o.estado !== "bloqueada" && o.estado !== "error");
  const pendingContacto = latest("contacto");
  const pendingVisita = latest("visita");
  const pendingTransicion = latest("transicion");

  if (cached === undefined) return <Spinner label="Cargando sitio" />;
  if (cached === null) {
    return (
      <main className="narrow">
        <Link to="/" className="back-link">
          <Icon name="arrow-left" size={16} /> Mis sitios
        </Link>
        <Alert tone="neutral" title="Este sitio no está en el teléfono">
          {sync.online ? "Sincroniza para descargarlo." : "Conéctate para consultarlo."}
        </Alert>
      </main>
    );
  }
  const s = cached.detail;
  const siguiente = nextEstatus(s.estatus);
  const completed = s.estatus === "recepcion_documentos";
  const terminal = !siguiente && !completed;
  const reqs = siguiente ? requisitos(s, siguiente, requiredDocs, pendingTipos) : [];
  const missing = reqs.filter((r) => !r.done);
  const canAdvance = !!siguiente && missing.length === 0 && !pendingTransicion;

  const contactoActual = (pendingContacto?.payload as ContactoIn | undefined) ?? s.contacto ?? null;
  const visitaActual = (pendingVisita?.payload as VisitaIn | undefined) ?? (s.visita as VisitaIn | null) ?? null;
  const showContactoForm = !contactoActual || editContacto;
  const showVisitaForm = !visitaActual || editVisita;

  async function afterServerChange() {
    await refreshSitio(sync.deps, sitioId);
    setRefreshKey(String(Date.now()));
  }
  async function guardarContacto(c: ContactoIn) {
    await sync.enqueueOp(sitioId, "contacto", c);
    setEditContacto(false);
    setFlash(sync.online ? "Contacto guardado y enviado." : "Contacto guardado en el teléfono; se enviará al recuperar señal.");
  }
  async function guardarVisita(v: VisitaIn) {
    await sync.enqueueOp(sitioId, "visita", v);
    setEditVisita(false);
    setFlash(sync.online ? "Medidas guardadas y enviadas." : "Medidas guardadas en el teléfono; se enviarán al recuperar señal.");
  }
  async function avanzar() {
    if (!siguiente) return;
    await sync.enqueueOp(sitioId, "transicion", { estatus_destino: siguiente, comentario: null });
    setFlash(sync.online ? `Avance a ${ESTATUS_LABELS[siguiente]} enviado.` : `Avance a ${ESTATUS_LABELS[siguiente]} guardado; se confirmará al sincronizar.`);
    setRefreshKey(String(Date.now()));
  }
  async function proponerDescarte() {
    if (comentarioDescarte.trim().length < 5) return;
    await sync.enqueueOp(sitioId, "transicion", { estatus_destino: "descartado", comentario: comentarioDescarte.trim() });
    setShowDescarte(false);
    setComentarioDescarte("");
    setFlash("Propuesta de descarte enviada al administrador.");
  }

  const mapsHref = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${s.lat},${s.lon}`)}`;

  return (
    <main className="narrow">
      <PageHeader
        title={s.nombre}
        back={
          <Link to="/" className="back-link">
            <Icon name="arrow-left" size={16} /> Mis sitios
          </Link>
        }
      >
        <div className="site-head">
          <div className="badges">
            <EstatusBadge estatus={s.estatus} devuelto={s.devuelto} />
            {pendingTransicion ? (
              <span className="pending" data-testid="pending-badge">
                <Icon name="clock" size={14} /> avance pendiente de sincronizar
              </span>
            ) : null}
            {s.en_revision_admin ? <span className="tag tag-info">en revisión del administrador</span> : null}
          </div>
          <StageIndicator estatus={s.estatus} />
          <dl className="meta" style={{ marginTop: "var(--space-3)" }}>
            <div>
              <dt>Número</dt>
              <dd>#{s.origen_id}</dd>
            </div>
            <div>
              <dt>Región</dt>
              <dd>{s.region}</dd>
            </div>
            <div>
              <dt>Potencial</dt>
              <dd>{potencialLabel(s.potencial)}</dd>
            </div>
            <div>
              <dt>Campos</dt>
              <dd>
                {s.campos_capturados}/{s.campos_total}
              </dd>
            </div>
            <div>
              <dt>Origen</dt>
              <dd>{formatMexicoCity(s.fecha_origen_utc)}</dd>
            </div>
          </dl>
          <div className="site-location">
            <span>
              <Icon name="map-pin" size={16} /> {s.lat}, {s.lon}
              {s.gps_texto ? ` · GPS ${s.gps_texto}` : ""}
            </span>
            <a href={mapsHref} target="_blank" rel="noopener noreferrer">
              Abrir en el mapa <Icon name="external" size={14} />
            </a>
          </div>
        </div>
      </PageHeader>

      {s.devuelto ? (
        <Alert tone="error" title="Devuelto por el administrador" testId="devuelto-banner">
          <p>
            <strong>{motivos[s.devolucion_motivo ?? ""] ?? s.devolucion_motivo ?? ""}</strong>
            {s.devolucion_comentario ? `: ${s.devolucion_comentario}` : ""}
          </p>
          <p>Corrige lo indicado y vuelve a avanzar el sitio.</p>
        </Alert>
      ) : null}
      {flash ? (
        <Alert tone="success" testId="flash" onClose={() => setFlash("")}>
          {flash}
        </Alert>
      ) : null}
      <ConflictPanel ops={ops} />

      <section className={`card${canAdvance ? " tone-attention" : ""}`} aria-labelledby="avance-h">
        <h2 id="avance-h">Siguiente paso</h2>
        {siguiente ? (
          <>
            <p className="section-sub">Para avanzar a {ESTATUS_LABELS[siguiente]} necesitas:</p>
            <ul className="checklist" data-testid={missing.length ? "precheck" : undefined}>
              {reqs.map((r) => (
                <li key={r.key} className={r.done ? "done" : "missing"}>
                  <Icon name={r.done ? "check-circle" : "alert-circle"} size={18} />
                  {r.done ? <span>{r.label}</span> : <a href={r.href}>{r.label}</a>}
                </li>
              ))}
            </ul>
            <button type="button" onClick={() => void avanzar()} disabled={!canAdvance} data-testid="avanzar">
              Avanzar a {ESTATUS_LABELS[siguiente]}
              <Icon name="arrow-right" size={18} />
            </button>
            {!canAdvance && missing.length ? (
              <p className="muted small" style={{ marginTop: "var(--space-2)" }}>
                Completa lo pendiente para habilitar el avance.
              </p>
            ) : null}
          </>
        ) : terminal ? (
          <p className="muted">El sitio está en un estatus final y ya no se edita.</p>
        ) : (
          <p className="muted">Completaste las etapas del coordinador. El administrador continúa con el sitio.</p>
        )}
      </section>

      <section className="card" aria-labelledby="contacto-h" id="contacto">
        <div className="card-head">
          <h2 id="contacto-h">Contacto del dueño</h2>
          {contactoActual && !showContactoForm && !terminal ? (
            <button type="button" className="ghost small" onClick={() => setEditContacto(true)}>
              <Icon name="edit" size={16} /> Editar
            </button>
          ) : null}
        </div>
        {pendingContacto ? (
          <p className="pending">
            <Icon name="clock" size={14} /> Pendiente de sincronizar
          </p>
        ) : null}
        {contactoActual && !showContactoForm ? (
          <dl className="summary">
            <dt>Nombre</dt>
            <dd>{contactoActual.nombre}</dd>
            <dt>Teléfono</dt>
            <dd>
              <a href={`tel:${contactoActual.telefono}`}>{contactoActual.telefono}</a>
            </dd>
            {contactoActual.correo ? (
              <>
                <dt>Correo</dt>
                <dd>{contactoActual.correo}</dd>
              </>
            ) : null}
            {contactoActual.notas ? (
              <>
                <dt>Notas</dt>
                <dd>{contactoActual.notas}</dd>
              </>
            ) : null}
            {s.contacto && !pendingContacto ? (
              <>
                <dt>Capturado</dt>
                <dd>{formatMexicoCity(s.contacto.capturado_utc)}</dd>
              </>
            ) : null}
          </dl>
        ) : (
          <ContactoForm
            key={`c-${cached.etag}-${pendingContacto?.id ?? ""}`}
            initial={contactoActual}
            onSubmit={guardarContacto}
            onCancel={contactoActual ? () => setEditContacto(false) : undefined}
            disabled={terminal}
          />
        )}
      </section>

      <section className="card" aria-labelledby="visita-h" id="visita">
        <div className="card-head">
          <h2 id="visita-h">Medidas del local</h2>
          {visitaActual && !showVisitaForm && !terminal ? (
            <button type="button" className="ghost small" onClick={() => setEditVisita(true)}>
              <Icon name="edit" size={16} /> Editar
            </button>
          ) : null}
        </div>
        {pendingVisita ? (
          <p className="pending">
            <Icon name="clock" size={14} /> Pendiente de sincronizar
          </p>
        ) : null}
        {visitaActual && !showVisitaForm ? (
          <dl className="summary">
            <dt>Frente</dt>
            <dd>{visitaActual.frente_m} m</dd>
            <dt>Fondo</dt>
            <dd>{visitaActual.fondo_m} m</dd>
            <dt>Área</dt>
            <dd>{visitaActual.area_m2 ? `${visitaActual.area_m2} m²` : "—"}</dd>
            <dt>Visita</dt>
            <dd>{formatMexicoCity(visitaActual.fecha_visita_utc)}</dd>
            {visitaActual.notas ? (
              <>
                <dt>Notas</dt>
                <dd>{visitaActual.notas}</dd>
              </>
            ) : null}
          </dl>
        ) : (
          <VisitaForm
            key={`v-${cached.etag}-${pendingVisita?.id ?? ""}`}
            initial={visitaActual}
            onSubmit={guardarVisita}
            onCancel={visitaActual ? () => setEditVisita(false) : undefined}
            disabled={terminal}
          />
        )}
      </section>

      <div className="card" id="fotos">
        <FotosSection sitioId={sitioId} publicadas={s.archivos.filter((a) => a.tipo === "foto" && a.vigente)} disabled={terminal} />
      </div>
      <div className="card" id="documentos">
        <DocumentosSection sitioId={sitioId} tipos={requiredDocs} archivos={s.archivos} onPublished={afterServerChange} disabled={terminal} />
      </div>
      <div className="card">
        <HistorialList sitioId={sitioId} refreshKey={`${refreshKey}-${cached.etag}`} />
      </div>

      {!terminal && !s.en_revision_admin ? (
        <details className="card more-actions" open={showDescarte}>
          <summary onClick={(e) => { e.preventDefault(); setShowDescarte((v) => !v); }}>
            <Icon name="more-horizontal" size={18} /> Más acciones
          </summary>
          <div style={{ marginTop: "var(--space-2)" }}>
            <h3>Proponer descarte</h3>
            <p className="muted small">Si el local ya no es viable (se rentó, el dueño no quiere, zona no apta), explícalo. El administrador decide.</p>
            <label htmlFor="descarte-comentario">Motivo del descarte</label>
            <textarea id="descarte-comentario" rows={2} value={comentarioDescarte} onChange={(e) => setComentarioDescarte(e.target.value)} maxLength={1000} />
            <p className="muted small">Mínimo 5 caracteres.</p>
            <div className="actions">
              <button type="button" className="danger" onClick={() => void proponerDescarte()} disabled={comentarioDescarte.trim().length < 5}>
                Enviar propuesta de descarte
              </button>
              <button type="button" className="ghost" onClick={() => setShowDescarte(false)}>
                Cancelar
              </button>
            </div>
          </div>
        </details>
      ) : null}
    </main>
  );
}
