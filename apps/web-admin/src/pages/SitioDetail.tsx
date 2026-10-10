import { ApiError } from "@pipeline/api-client";
import { ESTATUS_LABELS, EstatusBadge, ProblemAlert, Spinner, formatMexicoCity } from "@pipeline/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { useApi } from "../api";
import { Modal } from "../components/Modal";
import { esTerminal, estatusAnteriores } from "../lib/estatus";
import type { ArchivoOut, Catalogos, EquivalenciaOut, HistorialItem, SitioDetail } from "../lib/types";

type Dialog = "devolver" | "descartar" | "reasignar" | null;

export function SitioDetailPage() {
  const { id } = useParams();
  const api = useApi();
  const qc = useQueryClient();
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
  const equivalencias = useQuery({
    queryKey: ["equivalencias"],
    queryFn: () => api.get<EquivalenciaOut[]>("/api/v1/admin/equivalencias"),
  });

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

  return (
    <main>
      <p>
        <Link to="/sitios">← Sitios</Link>
      </p>
      <h1>
        {s.nombre} <span className="muted">#{s.origen_id}</span>
      </h1>
      <div className="row">
        <EstatusBadge estatus={s.estatus} devuelto={s.devuelto} />
        {s.en_revision_admin ? <span className="tag tag-advertencia">en revisión del administrador</span> : null}
        {!s.vigente ? <span className="tag">no vigente</span> : null}
      </div>
      {flash ? <div className="success" role="status">{flash}</div> : null}

      <div className="actions">
        <button type="button" disabled={terminal || estatusAnteriores(s.estatus).length === 0} onClick={() => setDialog("devolver")}>
          Devolver
        </button>
        <button type="button" className="danger" disabled={terminal} onClick={() => setDialog("descartar")}>
          Descartar
        </button>
        <button type="button" className="secondary" disabled={terminal} onClick={() => setDialog("reasignar")}>
          Reasignar
        </button>
      </div>

      <section className="card">
        <h2>Datos del sitio</h2>
        <dl className="props">
          <dt>Región</dt>
          <dd>{s.region}</dd>
          <dt>Coordinador</dt>
          <dd data-testid="detail-coordinador">
            {s.usuario_codigo} <span className="muted">{s.coordinador_oid}</span>
          </dd>
          <dt>Coordenadas</dt>
          <dd>
            {s.lat}, {s.lon}
          </dd>
          <dt>GPS (sin interpretar)</dt>
          <dd>{s.gps_texto ?? "—"}</dd>
          <dt>Potencial</dt>
          <dd>{s.potencial}</dd>
          <dt>Campos</dt>
          <dd>
            {s.campos_capturados}/{s.campos_total}
          </dd>
          <dt>Fecha origen</dt>
          <dd>{formatMexicoCity(s.fecha_origen_utc)}</dd>
          <dt>Actualizado</dt>
          <dd>{formatMexicoCity(s.actualizado_utc)}</dd>
          {s.devuelto ? (
            <>
              <dt>Devolución</dt>
              <dd data-testid="detail-devolucion">
                {s.devolucion_motivo}: {s.devolucion_comentario}
              </dd>
            </>
          ) : null}
          {s.en_revision_admin ? (
            <>
              <dt>Revisión</dt>
              <dd>{s.revision_detalle ?? "Pendiente de decisión del administrador"}</dd>
            </>
          ) : null}
        </dl>
      </section>

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

      <section className="card">
        <h2>Archivos</h2>
        {s.archivos.length === 0 ? <p className="muted">Sin archivos.</p> : <Archivos archivos={s.archivos} />}
      </section>

      <section className="card">
        <h2>Historial</h2>
        {historial.isError ? <ProblemAlert error={historial.error} /> : null}
        {historial.data ? (
          <div className="table-wrap">
            <table data-testid="historial">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Tipo</th>
                  <th>De</th>
                  <th>A</th>
                  <th>Motivo</th>
                  <th>Comentario</th>
                  <th>Origen</th>
                </tr>
              </thead>
              <tbody>
                {historial.data.map((h) => (
                  <tr key={h.id}>
                    <td className="nowrap">{formatMexicoCity(h.fecha_utc)}</td>
                    <td>{h.tipo}</td>
                    <td>{h.estatus_anterior ? ESTATUS_LABELS[h.estatus_anterior] ?? h.estatus_anterior : "—"}</td>
                    <td>{ESTATUS_LABELS[h.estatus_nuevo] ?? h.estatus_nuevo}</td>
                    <td>{h.motivo ?? ""}</td>
                    <td>{h.comentario ?? ""}</td>
                    <td>{h.origen}</td>
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

function Archivos({ archivos }: { archivos: ArchivoOut[] }) {
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
              <th>Tipo</th>
              <th>Documento</th>
              <th>Archivo</th>
              <th>Tamaño</th>
              <th>Páginas</th>
              <th>Versión</th>
              <th>Vigente</th>
              <th>Subido</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {archivos.map((a) => (
              <tr key={a.id}>
                <td>{a.tipo}</td>
                <td>{a.tipo_documento ?? "—"}</td>
                <td>{a.nombre_original}</td>
                <td className="nowrap">{(a.bytes / 1024 / 1024).toFixed(2)} MB</td>
                <td>{a.paginas ?? "—"}</td>
                <td>{a.version}</td>
                <td>{a.vigente ? "sí" : "no"}</td>
                <td className="nowrap">{formatMexicoCity(a.subido_utc)}</td>
                <td>
                  <button type="button" className="secondary" onClick={() => void download(a)}>
                    Descargar
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
  const [error, setError] = useState<unknown>(null);
  const mutation = useMutation({
    mutationFn: async ({ action, body, msg }: { action: string; body: unknown; msg: string }) => {
      await api.post(`/api/v1/admin/sitios/${sitioId}/${action}`, body, { ifMatch: etag });
      return msg;
    },
    onSuccess: (msg) => void onDone(msg),
    onError: (e) => setError(e),
  });
  const stale = error instanceof ApiError && error.isPreconditionFailed;
  return { mutation, error, stale };
}

function DevolverDialog({
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
      msg: `Sitio devuelto a ${ESTATUS_LABELS[destino] ?? destino}. El coordinador recibirá el aviso.`,
    });
  };
  return (
    <Modal title="Devolver a un estatus anterior" onClose={onClose} testId="dialog-devolver">
      <form onSubmit={submit}>
        <label>
          Estatus destino
          <select value={destino} onChange={(e) => setDestino(e.target.value)} name="estatus_destino" required>
            {anteriores.map((k) => (
              <option key={k} value={k}>
                {ESTATUS_LABELS[k]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Motivo
          <select value={motivo} onChange={(e) => setMotivo(e.target.value)} name="motivo" required>
            {catalogos.motivos_devolucion.map((m) => (
              <option key={m.codigo} value={m.codigo}>
                {m.nombre}
              </option>
            ))}
          </select>
        </label>
        <label>
          Comentario para el coordinador (mínimo 5 caracteres)
          <textarea
            name="comentario"
            value={comentario}
            minLength={5}
            maxLength={1000}
            required
            rows={3}
            onChange={(e) => setComentario(e.target.value)}
          />
        </label>
        {stale ? (
          <p role="alert" className="problem">
            El registro cambió desde que lo abriste. Cierra el diálogo para recargarlo e inténtalo de nuevo.
          </p>
        ) : (
          <ProblemAlert error={error} />
        )}
        <div className="actions">
          <button type="submit" disabled={mutation.isPending || comentario.trim().length < 5}>
            Devolver
          </button>
          <button type="button" className="secondary" onClick={onClose}>
            Cancelar
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
    <Modal title="Descartar sitio" onClose={onClose} testId="dialog-descartar">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({ action: "descartar", body: { motivo, comentario }, msg: "Sitio descartado." });
        }}
      >
        <p>El sitio pasa al estatus terminal Descartado. Los datos capturados se conservan.</p>
        <label>
          Motivo
          <select value={motivo} onChange={(e) => setMotivo(e.target.value)} name="motivo" required>
            {catalogos.motivos_devolucion.map((m) => (
              <option key={m.codigo} value={m.codigo}>
                {m.nombre}
              </option>
            ))}
          </select>
        </label>
        <label>
          Comentario (mínimo 5 caracteres)
          <textarea name="comentario" value={comentario} minLength={5} required rows={3} onChange={(e) => setComentario(e.target.value)} />
        </label>
        {stale ? <p role="alert" className="problem">El registro cambió. Recarga e inténtalo de nuevo.</p> : <ProblemAlert error={error} />}
        <div className="actions">
          <button type="submit" className="danger" disabled={mutation.isPending || comentario.trim().length < 5}>
            Descartar
          </button>
          <button type="button" className="secondary" onClick={onClose}>
            Cancelar
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
  return (
    <Modal title="Reasignar coordinador" onClose={onClose} testId="dialog-reasignar">
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
        <label>
          Nuevo coordinador
          <select value={oid} onChange={(e) => setOid(e.target.value)} name="coordinador_oid" required>
            {candidates.map((c) => (
              <option key={c.usuario_codigo} value={c.oid ?? ""}>
                {c.usuario_codigo} · {c.nombre ?? ""} ({c.correo})
              </option>
            ))}
          </select>
        </label>
        {candidates.length === 0 ? <p className="muted">No hay otros coordinadores activos con cuenta resuelta.</p> : null}
        {stale ? <p role="alert" className="problem">El registro cambió. Recarga e inténtalo de nuevo.</p> : <ProblemAlert error={error} />}
        <div className="actions">
          <button type="submit" disabled={mutation.isPending || !oid}>
            Reasignar
          </button>
          <button type="button" className="secondary" onClick={onClose}>
            Cancelar
          </button>
        </div>
      </form>
    </Modal>
  );
}
