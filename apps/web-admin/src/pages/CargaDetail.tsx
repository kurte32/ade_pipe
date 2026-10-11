import { ProblemAlert, Spinner, formatMexicoCity } from "@pipeline/ui";
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

  const detail = useQuery({
    queryKey: ["carga", id, resultado],
    queryFn: () =>
      api.get<LoteDetail>(`/api/v1/admin/cargas/${id}?limit=500${resultado ? `&resultado=${resultado}` : ""}`),
    enabled: !!id,
  });

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

  const invalidate = async () => {
    await qc.invalidateQueries({ queryKey: ["carga", id] });
    await qc.invalidateQueries({ queryKey: ["cargas"] });
  };

  const save = useMutation({
    mutationFn: async () => {
      const body = Object.entries(decisions).map(([n, d]) => ({ num_fila: Number(n), decision: d }));
      const r = await api.post<LoteSummary>(`/api/v1/admin/cargas/${id}/decisiones`, body);
      return r.data;
    },
    onSuccess: invalidate,
  });
  const confirm = useMutation({
    mutationFn: async () => (await api.post<ConfirmResult>(`/api/v1/admin/cargas/${id}/confirmar`)).data,
    onSuccess: async (r) => {
      setConfirmResult(r);
      await invalidate();
      await qc.invalidateQueries({ queryKey: ["sitios"] });
      await qc.invalidateQueries({ queryKey: ["resumen"] });
    },
  });
  const cancel = useMutation({
    mutationFn: async () => (await api.post<LoteSummary>(`/api/v1/admin/cargas/${id}/cancelar`)).data,
    onSuccess: invalidate,
  });

  if (detail.isPending) return <Spinner label="Cargando vista previa" />;
  if (detail.isError) return <ProblemAlert error={detail.error} onRetry={() => void detail.refetch()} />;
  if (!lote) return null;

  const setAll = (d: Decision) => {
    const next = { ...decisions };
    for (const w of warnings) next[w.num_fila] = d;
    setDecisions(next);
  };
  const savedAll = pendientes === 0;

  return (
    <main>
      <p>
        <Link to="/cargas">← Cargas</Link>
      </p>
      <h1>Vista previa: {lote.archivo_nombre}</h1>
      <p className="muted">
        {formatMexicoCity(lote.fecha_utc)} · hash {lote.hash.slice(0, 12)}… · estado <strong data-testid="lote-estado">{lote.estado}</strong>
      </p>
      <div className="cards" data-testid="lote-counts">
        <div className="card">
          <strong>{lote.filas_total}</strong>
          <span className="muted">filas</span>
        </div>
        <div className="card">
          <strong data-testid="count-ok">{lote.filas_ok}</strong>
          <span className="muted">ok</span>
        </div>
        <div className="card">
          <strong data-testid="count-advertencia">{lote.filas_advertencia}</strong>
          <span className="muted">advertencias</span>
        </div>
        <div className="card">
          <strong data-testid="count-error">{lote.filas_error}</strong>
          <span className="muted">errores (no se cargan)</span>
        </div>
        {editable ? (
          <div className="card">
            <strong data-testid="count-pendientes">{pendientes}</strong>
            <span className="muted">advertencias sin decisión</span>
          </div>
        ) : null}
      </div>

      {confirmResult ? (
        <div className="success" role="status" data-testid="confirm-result">
          Carga confirmada: {confirmResult.insertadas} sitios insertados, {confirmResult.actualizadas} actualizados,{" "}
          {confirmResult.revision} en revisión del administrador.
        </div>
      ) : null}
      {lote.estado === "confirmado" && !confirmResult ? (
        <div className="success" role="status">
          Confirmada el {formatMexicoCity(lote.confirmado_utc)}: {lote.filas_insertadas ?? 0} insertadas,{" "}
          {lote.filas_actualizadas ?? 0} actualizadas, {lote.filas_revision ?? 0} en revisión.
        </div>
      ) : null}

      {editable ? (
        <div className="actions">
          <button type="button" className="secondary" onClick={() => setAll("aprobar")} disabled={warnings.length === 0}>
            Aprobar todas las advertencias
          </button>
          <button type="button" className="secondary" onClick={() => setAll("excluir")} disabled={warnings.length === 0}>
            Excluir todas
          </button>
          <button
            type="button"
            onClick={() => save.mutate()}
            disabled={save.isPending || Object.keys(decisions).length === 0}
            data-testid="guardar-decisiones"
          >
            Guardar decisiones
          </button>
          <button
            type="button"
            onClick={() => confirm.mutate()}
            disabled={confirm.isPending || !savedAll || localPending > 0}
            title={!savedAll ? "Guarda una decisión para cada advertencia antes de confirmar" : ""}
            data-testid="confirmar-carga"
          >
            Confirmar carga
          </button>
          <button type="button" className="danger" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
            Cancelar
          </button>
        </div>
      ) : null}
      <ProblemAlert error={save.error ?? confirm.error ?? cancel.error} />

      <div className="filters">
        <label>
          Mostrar
          <select value={resultado} onChange={(e) => setResultado(e.target.value)} data-testid="filtro-resultado">
            <option value="">Todas</option>
            <option value="ok">Ok</option>
            <option value="advertencia">Advertencias</option>
            <option value="error">Errores</option>
          </select>
        </label>
      </div>

      <div className="table-wrap">
        <table data-testid="filas-table">
          <thead>
            <tr>
              <th>Fila</th>
              <th>#</th>
              <th>SITIO</th>
              <th>USUARIO</th>
              <th>REGIÓN</th>
              <th>Resultado</th>
              <th>Motivos</th>
              <th>Acción</th>
              <th>Decisión</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.num_fila} data-testid={`fila-${f.num_fila}`} data-resultado={f.resultado}>
                <td>{f.num_fila}</td>
                <td>{cell(f, "#")}</td>
                <td>{cell(f, "SITIO")}</td>
                <td>{cell(f, "USUARIO")}</td>
                <td>{cell(f, "REGION") || cell(f, "REGIÓN")}</td>
                <td>
                  <span className={`tag tag-${f.resultado}`}>{f.resultado}</span>
                </td>
                <td>
                  {f.motivos.map((m, i) => (
                    <div key={i}>
                      <code>{m["codigo"]}</code> {m["mensaje"]}
                    </div>
                  ))}
                </td>
                <td>{f.accion_prevista ?? ""}</td>
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
            ))}
          </tbody>
        </table>
        {rows.length === 0 ? <p className="muted">Sin filas para este filtro.</p> : null}
      </div>
    </main>
  );
}
