import { ApiError } from "@pipeline/api-client";
import {
  Alert,
  ESTATUS_LABELS,
  EstatusBadge,
  Field,
  HISTORIAL_ORIGEN,
  HISTORIAL_TIPO,
  Icon,
  Modal,
  PageHeader,
  ProblemAlert,
  Spinner,
  StageIndicator,
  formatMb,
  formatMexicoCity,
  label,
  potencialLabel,
  usePageTitle,
} from "@pipeline/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { useApi } from "../api";
import { useCoordinadores, useEquivalencias } from "../lib/equivalencias";
import { esTerminal, estatusAnteriores } from "../lib/estatus";
import type { ArchivoOut, Catalogos, EquivalenciaOut, HistorialItem, SitioDetail } from "../lib/types";

type Dialog = "devolver" | "descartar" | "reasignar" | null;

export function SitioDetailPage() {
  const { id } = useParams();
  const api = useApi();
  const qc = useQueryClient();
  const coords = useCoordinadores();
  const [dialog, setDialog] = useState<Dialog>(null);
  const [flash, setFlash] = useState<string>("");

  const detail = useQuery({
    queryKey: ["sitio", id],
    queryFn: () => api.get<SitioDetail>(`/api/v1/sitios/${id}`),
    enabled: !!id,
  });
  const historial = useQuery({
    queryKey: ["historial", id],
    queryFn: () => api.get<HistorialItem[]>(`/api/v1/sitios/${id}/historial`),
    enabled: !!id,
  });
  const catalogos = useQuery({ queryKey: ["catalogos"], queryFn: () => api.get<Catalogos>("/api/v1/catalogos") });
  const equivalencias = useEquivalencias();
  usePageTitle(detail.data?.nombre ?? "Sitio");

  const invalidate = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["sitio", id] }),
      qc.invalidateQueries({ queryKey: ["historial", id] }),
      qc.invalidateQueries({ queryKey: ["sitios"] }),
      qc.invalidateQueries({ queryKey: ["resumen"] }),
    ]);
  };

  if (detail.isPending) return <Spinner label="Cargando sitio" />;
  if (detail.isError) return <ProblemAlert error={detail.error} onRetry={() => void detail.refetch()} />;
  const s = detail.data;
  const terminal = esTerminal(s.estatus);
  const anteriores = estatusAnteriores(s.estatus);
  const motivos = Object.fromEntries((catalogos.data?.motivos_devolucion ?? []).map((m) => [m.codigo, m.nombre]));
  const docNames = Object.fromEntries((catalogos.data?.tipos_documento ?? []).map((t) => [t.id, t.nombre]));
  const coordinador = coords.byCode[s.usuario_codigo];
  const mapsHref = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${s.lat},${s.lon}`)}`;

  const why =
    terminal ? "El sitio está en un estatus final; ya no admite acciones." : anteriores.length === 0 ? "Está en la primera etapa: no hay un estatus anterior al cual devolverlo." : null;

  return (
    <main>
      <PageHeader
        back={
          <Link to="/sitios" className="back-link">
            <Icon name="arrow-left" size={16} /> Sitios
          </Link>
        }
        title={
          <>
            {s.nombre} <span className="muted">#{s.origen_id}</span>
          </>
        }
        actions={
          <>
            <button type="button" disabled={terminal || anteriores.length === 0} onClick={() => setDialog("devolver")}>
              <Icon name="arrow-left" size={16} /> Devolver
            </button>
            <button type="button" className="secondary" disabled={terminal} onClick={() => setDialog("reasignar")}>
              <Icon name="users" size={16} /> Reasignar
            </button>
            <button type="button" className="danger" disabled={terminal} onClick={() => setDialog("descartar")}>
              <Icon name="trash" size={16} /> Descartar
            </button>
          </>
        }
      >
        <div className="cluster" style={{ margin: "var(--space-2) 0" }}>
          <EstatusBadge estatus={s.estatus} devuelto={s.devuelto} />
          {s.en_revision_admin ? <span className="tag tag-warning">en revisión del administrador</span> : null}
          {!s.vigente ? <span className="tag tag-muted">no vigente</span> : null}
        </div>
        <StageIndicator estatus={s.estatus} />
        {why ? <p className="helper" style={{ marginTop: "var(--space-2)" }}>{why}</p> : null}
      </PageHeader>

      {flash ? (
        <Alert tone="success" onClose={() => setFlash("")}>
          {flash}
        </Alert>
      ) : null}
      {s.en_revision_admin ? (
        <Alert tone="warning" title="Pendiente de tu decisión" role="none">
          {String(s.revision_detalle ?? "").startsWith("Propuesta de descarte")
            ? "El coordinador propone descartar este sitio. Confírmalo con Descartar o devuélvelo con un motivo; mientras tanto no puede avanzarlo."
            : "Una carga asignó este sitio a otro coordinador después de que ya había avanzado. Reasígnalo, devuélvelo o descártalo; mientras tanto el coordinador no puede avanzarlo."}
          {s.revision_detalle ? <p className="small">{String(s.revision_detalle)}</p> : null}
        </Alert>
      ) : null}
      {s.devuelto ? (
        <Alert tone="error" title="Devuelto al coordinador" role="none">
          <span data-testid="detail-devolucion">
            {motivos[s.devolucion_motivo ?? ""] ?? s.devolucion_motivo}
            {s.devolucion_comentario ? ` · ${s.devolucion_comentario}` : ""}
          </span>
        </Alert>
      ) : null}

      <div className="two-col">
        <section className="card">
          <h2>Datos del sitio</h2>
          <dl className="props">
            <dt>Región</dt>
            <dd>{s.region}</dd>
            <dt>Coordinador</dt>
            <dd data-testid="detail-coordinador" title={s.coordinador_oid ?? undefined}>
              {s.usuario_codigo}
              {coordinador?.nombre ? ` · ${coordinador.nombre}` : ""}
            </dd>
            <dt>Ubicación</dt>
            <dd>
              {s.lat}, {s.lon}{" "}
              <a href={mapsHref} target="_blank" rel="noopener noreferrer">
                Abrir en el mapa <Icon name="external" size={12} />
              </a>
            </dd>
            <dt>GPS del archivo</dt>
            <dd>{s.gps_texto ?? "—"}</dd>
            <dt>Potencial</dt>
            <dd>{potencialLabel(s.potencial)}</dd>
            <dt>Campos</dt>
            <dd title="Campos con dato en el archivo de origen">
              {s.campos_capturados}/{s.campos_total}
            </dd>
            <dt>Fecha origen</dt>
            <dd>{formatMexicoCity(s.fecha_origen_utc)}</dd>
            <dt>Actualizado</dt>
            <dd>{formatMexicoCity(s.actualizado_utc)}</dd>
          </dl>
        </section>

        <div className="stack">
          <section className="card">
            <h2>Contacto del dueño</h2>
            {s.contacto ? (
              <dl className="props">
                <dt>Nombre</dt>
                <dd>{s.contacto.nombre}</dd>
                <dt>Teléfono</dt>
                <dd>{s.contacto.telefono}</dd>
                <dt>Correo</dt>
                <dd>{s.contacto.correo ?? "—"}</dd>
                <dt>Notas</dt>
                <dd>{s.contacto.notas ?? "—"}</dd>
                <dt>Capturado</dt>
                <dd>{formatMexicoCity(s.contacto.capturado_utc)}</dd>
              </dl>
            ) : (
              <p className="muted">Sin contacto capturado.</p>
            )}
          </section>
          <section className="card">
            <h2>Primera visita</h2>
            {s.visita ? (
              <dl className="props">
                <dt>Frente</dt>
                <dd>{s.visita.frente_m} m</dd>
                <dt>Fondo</dt>
                <dd>{s.visita.fondo_m} m</dd>
                <dt>Área</dt>
                <dd>{s.visita.area_m2 ? `${s.visita.area_m2} m²` : "—"}</dd>
                <dt>Fecha</dt>
                <dd>{formatMexicoCity(s.visita.fecha_visita_utc)}</dd>
                <dt>Notas</dt>
                <dd>{s.visita.notas ?? "—"}</dd>
              </dl>
            ) : (
              <p className="muted">Sin medidas capturadas.</p>
            )}
          </section>
        </div>
      </div>

      <section className="card" style={{ marginTop: "var(--space-3)" }}>
        <h2>Archivos</h2>
        {s.archivos.length === 0 ? <p className="muted">Sin fotos ni documentos todavía.</p> : <Archivos archivos={s.archivos} docNames={docNames} />}
      </section>

      <section className="card">
        <h2>Historial</h2>
        {historial.isError ? <ProblemAlert error={historial.error} /> : null}
        {historial.data ? (
          <div className="table-wrap">
            <table data-testid="historial">
              <thead>
                <tr>
                  <th scope="col">Fecha</th>
                  <th scope="col">Movimiento</th>
                  <th scope="col">De</th>
                  <th scope="col">A</th>
                  <th scope="col">Motivo</th>
                  <th scope="col">Comentario</th>
                  <th scope="col">Origen</th>
                </tr>
              </thead>
              <tbody>
                {historial.data.map((h) => (
                  <tr key={h.id}>
                    <td className="nowrap">{formatMexicoCity(h.fecha_utc)}</td>
                    <td>{label(HISTORIAL_TIPO, h.tipo)}</td>
                    <td>{h.estatus_anterior ? (ESTATUS_LABELS[h.estatus_anterior] ?? h.estatus_anterior) : "—"}</td>
                    <td>{ESTATUS_LABELS[h.estatus_nuevo] ?? h.estatus_nuevo}</td>
                    <td>{h.motivo ? (motivos[h.motivo] ?? h.motivo) : ""}</td>
                    <td>{h.comentario ?? ""}</td>
                    <td>{label(HISTORIAL_ORIGEN, h.origen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      {dialog === "devolver" && catalogos.data ? (
        <DevolverDialog
          sitio={s}
          catalogos={catalogos.data}
          coordinador={coordinador?.nombre ?? s.usuario_codigo}
          onClose={() => setDialog(null)}
          onDone={async (msg) => {
            setDialog(null);
            setFlash(msg);
            await invalidate();
          }}
        />
      ) : null}
      {dialog === "descartar" && catalogos.data ? (
        <DescartarDialog
          sitio={s}
          catalogos={catalogos.data}
          onClose={() => setDialog(null)}
          onDone={async (msg) => {
            setDialog(null);
            setFlash(msg);
            await invalidate();
          }}
        />
      ) : null}
      {dialog === "reasignar" && equivalencias.data ? (
        <ReasignarDialog
          sitio={s}
          equivalencias={equivalencias.data}
          onClose={() => setDialog(null)}
          onDone={async (msg) => {
            setDialog(null);
            setFlash(msg);
            await invalidate();
          }}
        />
      ) : null}
    </main>
  );
}

function Archivos({ archivos, docNames }: { archivos: ArchivoOut[]; docNames: Record<string, string> }) {
  const api = useApi();
  const [error, setError] = useState<unknown>(null);
  const download = async (a: ArchivoOut) => {
    try {
      const res = await api.fetchRaw(`/api/v1/archivos/${a.id}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = a.nombre_original;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (e) {
      setError(e);
    }
  };
  return (
    <>
      <ProblemAlert error={error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Tipo</th>
              <th scope="col">Archivo</th>
              <th scope="col" className="num">
                Tamaño
              </th>
              <th scope="col" className="num">
                Páginas
              </th>
              <th scope="col">Versión</th>
              <th scope="col">Subido</th>
              <th scope="col">
                <span className="visually-hidden">Acciones</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {archivos.map((a) => (
              <tr key={a.id}>
                <td>
                  {a.tipo === "foto" ? "Foto" : (docNames[a.tipo_documento ?? ""] ?? a.tipo_documento ?? "Documento")}
                  {!a.vigente ? <span className="tag tag-muted" style={{ marginLeft: 6 }}>anterior</span> : null}
                </td>
                <td style={{ overflowWrap: "anywhere" }}>{a.nombre_original}</td>
                <td className="num nowrap">{formatMb(a.bytes)}</td>
                <td className="num">{a.paginas ?? "—"}</td>
                <td>v{a.version}</td>
                <td className="nowrap">{formatMexicoCity(a.subido_utc)}</td>
                <td>
                  <button type="button" className="ghost small" onClick={() => void download(a)}>
                    <Icon name="download" size={16} /> Descargar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function useAdminAction(sitioId: number, etag: string, onDone: (msg: string) => Promise<void>) {
  const api = useApi();
  const qc = useQueryClient();
  const [error, setError] = useState<unknown>(null);
  const mutation = useMutation({
    mutationFn: async ({ action, body, msg }: { action: string; body: unknown; msg: string }) => {
      await api.post(`/api/v1/admin/sitios/${sitioId}/${action}`, body, { ifMatch: etag });
      return msg;
    },
    onSuccess: (msg) => void onDone(msg),
    onError: (e) => {
      setError(e);
      // A 412 means our copy is stale: reload it now so the next submit carries the current
      // ETag, instead of looping on the same stale one (audit FE-7).
      if (e instanceof ApiError && e.isPreconditionFailed) {
        void qc.invalidateQueries({ queryKey: ["sitio", String(sitioId)] });
        void qc.invalidateQueries({ queryKey: ["historial", String(sitioId)] });
      }
    },
  });
  const stale = error instanceof ApiError && error.isPreconditionFailed;
  return { mutation, error, stale };
}

function StaleOrError({ stale, error }: { stale: boolean; error: unknown }) {
  if (stale) {
    return (
      <Alert tone="error" title="El registro cambió desde que lo abriste">
        El sitio se volvió a cargar con los datos actuales; revísalos e inténtalo de nuevo.
      </Alert>
    );
  }
  return <ProblemAlert error={error} />;
}

function DevolverDialog({
  sitio,
  catalogos,
  coordinador,
  onClose,
  onDone,
}: {
  sitio: SitioDetail;
  catalogos: Catalogos;
  coordinador: string;
  onClose: () => void;
  onDone: (msg: string) => Promise<void>;
}) {
  const anteriores = estatusAnteriores(sitio.estatus);
  const [destino, setDestino] = useState(anteriores[anteriores.length - 1] ?? "");
  const [motivo, setMotivo] = useState(catalogos.motivos_devolucion[0]?.codigo ?? "");
  const [comentario, setComentario] = useState("");
  const { mutation, error, stale } = useAdminAction(sitio.id, sitio.etag, onDone);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      action: "devolver",
      body: { estatus_destino: destino, motivo, comentario },
      msg: `Sitio devuelto a ${ESTATUS_LABELS[destino] ?? destino}. ${coordinador} recibirá el aviso.`,
    });
  };
  return (
    <Modal
      title="Devolver a un estatus anterior"
      lede={`${sitio.nombre} regresa a la etapa que elijas y ${coordinador} recibe un aviso con el motivo y tu comentario.`}
      onClose={onClose}
      testId="dialog-devolver"
      dismissOnBackdrop={comentario.length === 0}
    >
      <form onSubmit={submit}>
        <Field id="dv-destino" label="Estatus destino">
          <select value={destino} onChange={(e) => setDestino(e.target.value)} name="estatus_destino" required>
            {anteriores.map((k) => (
              <option key={k} value={k}>
                {ESTATUS_LABELS[k]}
              </option>
            ))}
          </select>
        </Field>
        <Field id="dv-motivo" label="Motivo">
          <select value={motivo} onChange={(e) => setMotivo(e.target.value)} name="motivo" required>
            {catalogos.motivos_devolucion.map((m) => (
              <option key={m.codigo} value={m.codigo}>
                {m.nombre}
              </option>
            ))}
          </select>
        </Field>
        <Field id="dv-comentario" label="Comentario para el coordinador" hint="Qué debe corregir. Mínimo 5 caracteres.">
          <textarea name="comentario" value={comentario} minLength={5} maxLength={1000} required rows={3} onChange={(e) => setComentario(e.target.value)} />
        </Field>
        <StaleOrError stale={stale} error={error} />
        <div className="actions">
          <button type="button" className="ghost" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" disabled={mutation.isPending || comentario.trim().length < 5}>
            {mutation.isPending ? "Devolviendo…" : "Devolver"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function DescartarDialog({
  sitio,
  catalogos,
  onClose,
  onDone,
}: {
  sitio: SitioDetail;
  catalogos: Catalogos;
  onClose: () => void;
  onDone: (msg: string) => Promise<void>;
}) {
  const [motivo, setMotivo] = useState(catalogos.motivos_devolucion[0]?.codigo ?? "");
  const [comentario, setComentario] = useState("");
  const { mutation, error, stale } = useAdminAction(sitio.id, sitio.etag, onDone);
  return (
    <Modal
      title="Descartar sitio"
      lede={`${sitio.nombre} pasa al estatus final Descartado y sale del pipeline. Los datos capturados se conservan. No se puede deshacer desde la aplicación.`}
      onClose={onClose}
      testId="dialog-descartar"
      dismissOnBackdrop={comentario.length === 0}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({ action: "descartar", body: { motivo, comentario }, msg: "Sitio descartado." });
        }}
      >
        <Field id="ds-motivo" label="Motivo">
          <select value={motivo} onChange={(e) => setMotivo(e.target.value)} name="motivo" required>
            {catalogos.motivos_devolucion.map((m) => (
              <option key={m.codigo} value={m.codigo}>
                {m.nombre}
              </option>
            ))}
          </select>
        </Field>
        <Field id="ds-comentario" label="Comentario" hint="Mínimo 5 caracteres. Queda en el historial del sitio.">
          <textarea name="comentario" value={comentario} minLength={5} required rows={3} onChange={(e) => setComentario(e.target.value)} />
        </Field>
        <StaleOrError stale={stale} error={error} />
        <div className="actions">
          <button type="button" className="ghost" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" className="danger" disabled={mutation.isPending || comentario.trim().length < 5}>
            {mutation.isPending ? "Descartando…" : "Descartar sitio"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ReasignarDialog({
  sitio,
  equivalencias,
  onClose,
  onDone,
}: {
  sitio: SitioDetail;
  equivalencias: EquivalenciaOut[];
  onClose: () => void;
  onDone: (msg: string) => Promise<void>;
}) {
  const candidates = equivalencias.filter((e) => e.activo && e.oid && e.oid !== sitio.coordinador_oid);
  const [oid, setOid] = useState(candidates[0]?.oid ?? "");
  const { mutation, error, stale } = useAdminAction(sitio.id, sitio.etag, onDone);
  const actual = equivalencias.find((e) => e.oid === sitio.coordinador_oid);
  return (
    <Modal
      title="Reasignar coordinador"
      lede={`Hoy ${sitio.nombre} está asignado a ${actual?.nombre ?? sitio.usuario_codigo}. El nuevo coordinador lo verá en su app en la siguiente sincronización y el anterior dejará de verlo.`}
      onClose={onClose}
      testId="dialog-reasignar"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const target = candidates.find((c) => c.oid === oid);
          mutation.mutate({
            action: "reasignar",
            body: { coordinador_oid: oid },
            msg: `Sitio reasignado a ${target?.nombre ?? target?.usuario_codigo ?? "otro coordinador"}.`,
          });
        }}
      >
        <Field id="rs-oid" label="Nuevo coordinador">
          <select value={oid} onChange={(e) => setOid(e.target.value)} name="coordinador_oid" required>
            {candidates.map((c) => (
              <option key={c.usuario_codigo} value={c.oid ?? ""}>
                {c.usuario_codigo} · {c.nombre ?? ""} ({c.correo})
              </option>
            ))}
          </select>
        </Field>
        {candidates.length === 0 ? <p className="muted">No hay otros coordinadores activos con cuenta resuelta.</p> : null}
        <StaleOrError stale={stale} error={error} />
        <div className="actions">
          <button type="button" className="ghost" onClick={onClose}>
            Cancelar
          </button>
          <button type="submit" disabled={mutation.isPending || !oid}>
            {mutation.isPending ? "Reasignando…" : "Reasignar"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
