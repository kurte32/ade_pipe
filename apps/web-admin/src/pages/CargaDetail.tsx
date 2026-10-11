import { ACCION_PREVISTA, Alert, FILA_RESULTADO, Icon, LOTE_ESTADO, Modal, PageHeader, ProblemAlert, Spinner, formatMexicoCity, label, usePageTitle } from "@pipeline/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useApi } from "../api";
import type { ConfirmResult, FilaOut, LoteDetail, LoteSummary } from "../lib/types";

type Decision = "aprobar" | "excluir";

function cell(f: FilaOut, key: string): string {
  const v = f.datos[key];
  return v === null || v === undefined ? "" : String(v);
}

export function CargaDetail() {
  const { id } = useParams();
  const api = useApi();
  const qc = useQueryClient();
  const [resultado, setResultado] = useState<string>("");
  const [decisions, setDecisions] = useState<Record<number, Decision>>({});
  const [confirmResult, setConfirmResult] = useState<ConfirmResult | null>(null);
  const [askCancel, setAskCancel] = useState(false);

  const detail = useQuery({
    queryKey: ["carga", id, resultado],
    // Every page, not the first 500 rows: a warning past the first page was undecidable and
    // "Confirmar" was enabled only to fail with 422 (audit FE-8). Loads are capped at 5000 rows.
    queryFn: async () => {
      const items: LoteDetail["filas"]["items"] = [];
      let cursor: string | null = null;
      let lote: LoteDetail["lote"] | null = null;
      do {
        const page: LoteDetail = await api.get<LoteDetail>(
          `/api/v1/admin/cargas/${id}?limit=500${resultado ? `&resultado=${resultado}` : ""}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
        );
        lote = page.lote;
        items.push(...page.filas.items);
        cursor = page.filas.next_cursor ?? null;
      } while (cursor);
      return { lote: lote!, filas: { items, next_cursor: null } } as LoteDetail;
    },
    enabled: !!id,
  });
  usePageTitle(detail.data ? `Carga ${detail.data.lote.archivo_nombre}` : "Carga");

  // Seed local decisions from the server state when rows load.
  useEffect(() => {
    if (!detail.data) return;
    setDecisions((prev) => {
      const next = { ...prev };
      for (const f of detail.data.filas.items) {
        if (f.decision_admin && next[f.num_fila] === undefined) next[f.num_fila] = f.decision_admin as Decision;
      }
      return next;
    });
  }, [detail.data]);

  const lote = detail.data?.lote;
  const rows = detail.data?.filas.items ?? [];
  const editable = lote?.estado === "vista_previa";

  const warnings = useMemo(() => rows.filter((r) => r.resultado === "advertencia"), [rows]);
  const pendientes = lote ? lote.pendientes_decision : 0;
  const localPending = warnings.filter((w) => !decisions[w.num_fila]).length;
  const unsaved = useMemo(() => rows.some((r) => r.resultado === "advertencia" && decisions[r.num_fila] && decisions[r.num_fila] !== r.decision_admin), [rows, decisions]);

  const invalidate = async () => {
    await qc.invalidateQueries({ queryKey: ["carga", id] });
    await qc.invalidateQueries({ queryKey: ["cargas"] });
  };

  const saveDecisions = async () => {
    const body = Object.entries(decisions).map(([n, d]) => ({ num_fila: Number(n), decision: d }));
    if (body.length === 0) return;
    await api.post<LoteSummary>(`/api/v1/admin/cargas/${id}/decisiones`, body);
  };
  const save = useMutation({ mutationFn: saveDecisions, onSuccess: invalidate });
  const confirm = useMutation({
    // Saving the decisions first and then confirming keeps the two API calls and removes a click.
    mutationFn: async () => {
      if (unsaved || (pendientes > 0 && localPending === 0)) await saveDecisions();
      return (await api.post<ConfirmResult>(`/api/v1/admin/cargas/${id}/confirmar`)).data;
    },
    onSuccess: async (r) => {
      setConfirmResult(r);
      await invalidate();
      await qc.invalidateQueries({ queryKey: ["sitios"] });
      await qc.invalidateQueries({ queryKey: ["resumen"] });
    },
  });
  const cancel = useMutation({
    mutationFn: async () => (await api.post<LoteSummary>(`/api/v1/admin/cargas/${id}/cancelar`)).data,
    onSuccess: async () => {
      setAskCancel(false);
      await invalidate();
    },
  });

  if (detail.isPending) return <Spinner label="Cargando vista previa" />;
  if (detail.isError) return <ProblemAlert error={detail.error} onRetry={() => void detail.refetch()} />;
  if (!lote) return null;

  const setAll = (d: Decision) => {
    const next = { ...decisions };
    for (const w of warnings) next[w.num_fila] = d;
    setDecisions(next);
  };
  const canConfirm = editable && localPending === 0 && !confirm.isPending;
  const estado = LOTE_ESTADO[lote.estado] ?? { label: lote.estado, tone: "" };
  const filtroCounts: Record<string, number> = { "": lote.filas_total, ok: lote.filas_ok, advertencia: lote.filas_advertencia, error: lote.filas_error };

  return (
    <main>
      <PageHeader
        back={
          <Link to="/cargas" className="back-link">
            <Icon name="arrow-left" size={16} /> Cargas
          </Link>
        }
        title={lote.archivo_nombre}
        description={
          <>
            {formatMexicoCity(lote.fecha_utc)} · huella <code>{lote.hash.slice(0, 12)}…</code>
          </>
        }
      >
        <div className="cluster" style={{ marginTop: "var(--space-2)" }}>
          <span className={`tag ${estado.tone}`}>
            Estado: <span data-testid="lote-estado">{estado.label}</span>
          </span>
        </div>
      </PageHeader>

      {editable ? (
        <ol className="steps">
          <li className="done">Archivo cargado</li>
          <li className={localPending > 0 ? "current" : "done"}>Decide las advertencias</li>
          <li className={localPending === 0 ? "current" : ""}>Confirma la carga</li>
        </ol>
      ) : null}

      <div className="stats" data-testid="lote-counts">
        <div className="stat">
          <strong>{lote.filas_total}</strong>
          <span>filas</span>
        </div>
        <div className="stat is-ok">
          <strong data-testid="count-ok">{lote.filas_ok}</strong>
          <span>correctas</span>
        </div>
        <div className="stat is-warning">
          <strong data-testid="count-advertencia">{lote.filas_advertencia}</strong>
          <span>advertencias</span>
        </div>
        <div className="stat is-error">
          <strong data-testid="count-error">{lote.filas_error}</strong>
          <span>errores (no se cargan)</span>
        </div>
        {editable ? (
          <div className={`stat${pendientes ? " is-warning" : ""}`}>
            <strong data-testid="count-pendientes">{pendientes}</strong>
            <span>advertencias sin decisión guardada</span>
          </div>
        ) : null}
      </div>

      {confirmResult ? (
        <Alert tone="success" title="Carga confirmada" testId="confirm-result">
          {confirmResult.insertadas} sitios insertados, {confirmResult.actualizadas} actualizados, {confirmResult.revision} en revisión del administrador.
        </Alert>
      ) : null}
      {lote.estado === "confirmado" && !confirmResult ? (
        <Alert tone="success" title={`Confirmada el ${formatMexicoCity(lote.confirmado_utc)}`}>
          {lote.filas_insertadas ?? 0} insertadas, {lote.filas_actualizadas ?? 0} actualizadas, {lote.filas_revision ?? 0} en revisión.
        </Alert>
      ) : null}
      {lote.estado === "cancelado" ? (
        <Alert tone="neutral" title="Carga cancelada">
          Ningún sitio se insertó ni actualizó.
        </Alert>
      ) : null}
      <ProblemAlert error={save.error ?? confirm.error ?? cancel.error} />

      <div className="chips" role="group" aria-label="Mostrar filas" data-testid="filtro-resultado" style={{ margin: "var(--space-3) 0" }}>
        {[
          ["", "Todas"],
          ["ok", "Correctas"],
          ["advertencia", "Advertencias"],
          ["error", "Errores"],
        ].map(([v, l]) => (
          <button key={v} type="button" className="chip" aria-pressed={resultado === v} onClick={() => setResultado(v!)}>
            {l} <span className="n">{filtroCounts[v!] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="table-wrap">
        <table data-testid="filas-table">
          <thead>
            <tr>
              <th scope="col" className="num">
                Fila
              </th>
              <th scope="col" className="num">
                #
              </th>
              <th scope="col">Sitio</th>
              <th scope="col">Usuario</th>
              <th scope="col">Región</th>
              <th scope="col">Resultado</th>
              <th scope="col">Motivos</th>
              <th scope="col">Acción prevista</th>
              <th scope="col">Decisión</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => {
              const r = FILA_RESULTADO[f.resultado] ?? { label: f.resultado, tone: "" };
              return (
                <tr key={f.num_fila} data-testid={`fila-${f.num_fila}`} data-resultado={f.resultado}>
                  <td className="num">{f.num_fila}</td>
                  <td className="num">{cell(f, "#")}</td>
                  <td>{cell(f, "SITIO")}</td>
                  <td>{cell(f, "USUARIO")}</td>
                  <td>{cell(f, "REGION") || cell(f, "REGIÓN")}</td>
                  <td>
                    <span className={`tag ${r.tone}`}>{r.label}</span>
                  </td>
                  <td>
                    {f.motivos.map((m, i) => (
                      <span className="motivo" key={i}>
                        {String(m["mensaje"] ?? "")}
                        <code>{String(m["codigo"] ?? "")}</code>
                      </span>
                    ))}
                  </td>
                  <td>{label(ACCION_PREVISTA, f.accion_prevista)}</td>
                  <td>
                    {f.resultado === "advertencia" ? (
                      <select
                        aria-label={`Decisión fila ${f.num_fila}`}
                        value={decisions[f.num_fila] ?? ""}
                        disabled={!editable}
                        onChange={(e) => setDecisions({ ...decisions, [f.num_fila]: e.target.value as Decision })}
                      >
                        <option value="">Sin decisión</option>
                        <option value="aprobar">Aprobar</option>
                        <option value="excluir">Excluir</option>
                      </select>
                    ) : f.resultado === "error" ? (
                      <span className="muted">no se puede aprobar</span>
                    ) : (
                      ""
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 ? <p className="muted" style={{ padding: "var(--space-4)" }}>Sin filas para este filtro.</p> : null}
      </div>

      {editable ? (
        <div className="action-bar" role="region" aria-label="Acciones de la carga">
          <button type="button" className="secondary small" onClick={() => setAll("aprobar")} disabled={warnings.length === 0}>
            Aprobar todas las advertencias
          </button>
          <button type="button" className="secondary small" onClick={() => setAll("excluir")} disabled={warnings.length === 0}>
            Excluir todas
          </button>
          <button type="button" className="secondary small" onClick={() => save.mutate()} disabled={save.isPending || Object.keys(decisions).length === 0} data-testid="guardar-decisiones">
            {save.isPending ? "Guardando…" : unsaved ? "Guardar decisiones" : "Decisiones guardadas"}
          </button>
          <span className="spacer" />
          <button type="button" className="danger small" onClick={() => setAskCancel(true)} disabled={cancel.isPending}>
            Cancelar carga
          </button>
          <button type="button" onClick={() => confirm.mutate()} disabled={!canConfirm} data-testid="confirmar-carga">
            <Icon name="check" size={16} />
            {confirm.isPending ? "Confirmando…" : "Confirmar carga"}
          </button>
          <span className="hint">
            {localPending > 0
              ? `Decide ${localPending} advertencia${localPending === 1 ? "" : "s"} (aprobar o excluir) para poder confirmar. Los errores nunca se cargan.`
              : unsaved
                ? "Al confirmar se guardan las decisiones pendientes y se insertan o actualizan los sitios."
                : "Al confirmar se insertan o actualizan los sitios. Los errores se omiten."}
          </span>
        </div>
      ) : null}

      {askCancel ? (
        <Modal title="Cancelar esta carga" lede="La vista previa se descarta y ningún sitio se inserta ni actualiza. Puedes volver a subir el archivo después." onClose={() => setAskCancel(false)} testId="dialog-cancelar">
          <ProblemAlert error={cancel.error} />
          <div className="actions">
            <button type="button" className="ghost" onClick={() => setAskCancel(false)}>
              Volver
            </button>
            <button type="button" className="danger" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
              {cancel.isPending ? "Cancelando…" : "Cancelar carga"}
            </button>
          </div>
        </Modal>
      ) : null}
    </main>
  );
}
