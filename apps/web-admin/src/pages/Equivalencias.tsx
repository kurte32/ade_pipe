import { ApiError } from "@pipeline/api-client";
import { Alert, Icon, PageHeader, ProblemAlert, Spinner, formatMexicoCity, usePageTitle } from "@pipeline/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { useApi } from "../api";
import type { EquivalenciaOut } from "../lib/types";

interface Row {
  usuario_codigo: string;
  correo: string;
  activo: boolean;
  nombre: string | null;
  oid: string | null;
  actualizado_utc: string | null;
  isNew?: boolean;
}

function toRows(data: EquivalenciaOut[]): Row[] {
  return data.map((e) => ({ ...e, actualizado_utc: e.actualizado_utc }));
}

export function Equivalencias() {
  usePageTitle("Equivalencias");
  const api = useApi();
  const qc = useQueryClient();
  const [rows, setRows] = useState<Row[]>([]);
  const [saved, setSaved] = useState(false);

  const q = useQuery({
    queryKey: ["equivalencias"],
    queryFn: () => api.get<EquivalenciaOut[]>("/api/v1/admin/equivalencias"),
  });
  useEffect(() => {
    if (q.data) setRows(toRows(q.data));
  }, [q.data]);

  const dirty = useMemo(() => {
    if (!q.data) return false;
    const base = toRows(q.data);
    if (rows.length !== base.length) return true;
    return rows.some((r, i) => r.isNew || r.correo !== base[i]?.correo || r.activo !== base[i]?.activo);
  }, [rows, q.data]);

  const save = useMutation({
    mutationFn: async () => {
      const body = rows
        .filter((r) => r.usuario_codigo && r.correo)
        .map((r) => ({ usuario_codigo: r.usuario_codigo.trim().toLowerCase(), correo: r.correo.trim(), activo: r.activo }));
      return (await api.put<EquivalenciaOut[]>("/api/v1/admin/equivalencias", body)).data;
    },
    onSuccess: async () => {
      setSaved(true);
      await qc.invalidateQueries({ queryKey: ["equivalencias"] });
    },
    onError: () => setSaved(false),
  });

  const perCodeErrors: Record<string, string> = {};
  if (save.error instanceof ApiError && Array.isArray(save.error.problem?.["errors"])) {
    for (const e of save.error.problem["errors"] as { usuario_codigo?: string; mensaje?: string }[]) {
      if (e.usuario_codigo) perCodeErrors[e.usuario_codigo] = e.mensaje ?? "error";
    }
  }

  const update = (i: number, patch: Partial<Row>) => {
    setSaved(false);
    setRows(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  };
  const removeNew = (i: number) => setRows(rows.filter((_, idx) => idx !== i));
  const unresolved = rows.filter((r) => !r.isNew && !r.oid).length;

  return (
    <main>
      <PageHeader
        title="Equivalencias de coordinadores"
        description="Cada código USUARIO del archivo de carga corresponde a una cuenta corporativa. La cuenta se resuelve al guardar; si un correo no existe, no se guarda ninguna fila. Todo cambio queda en la bitácora."
      />
      {q.isPending ? <Spinner /> : null}
      {q.isError ? <ProblemAlert error={q.error} onRetry={() => void q.refetch()} /> : null}
      {q.data ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          {unresolved ? (
            <Alert tone="warning" role="none">
              {unresolved} código{unresolved === 1 ? "" : "s"} sin cuenta resuelta: las cargas con ese USUARIO quedarán en error hasta corregir el correo.
            </Alert>
          ) : null}
          <div className="table-wrap">
            <table data-testid="equivalencias-table">
              <thead>
                <tr>
                  <th scope="col">Código</th>
                  <th scope="col">Correo corporativo</th>
                  <th scope="col">Nombre</th>
                  <th scope="col">Cuenta</th>
                  <th scope="col">Activo</th>
                  <th scope="col">Actualizado</th>
                  <th scope="col">
                    <span className="visually-hidden">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.isNew ? `new-${i}` : r.usuario_codigo} data-testid={`eq-${r.usuario_codigo || "nuevo"}`}>
                    <td>
                      {r.isNew ? (
                        <input
                          aria-label="Código"
                          value={r.usuario_codigo}
                          pattern="[a-z]{3,10}"
                          placeholder="abc"
                          style={{ width: 90 }}
                          onChange={(e) => update(i, { usuario_codigo: e.target.value })}
                        />
                      ) : (
                        <code>{r.usuario_codigo}</code>
                      )}
                    </td>
                    <td>
                      <input
                        type="email"
                        aria-label={`Correo ${r.usuario_codigo}`}
                        aria-invalid={perCodeErrors[r.usuario_codigo] ? true : undefined}
                        value={r.correo}
                        style={{ minWidth: 220 }}
                        onChange={(e) => update(i, { correo: e.target.value })}
                      />
                      {perCodeErrors[r.usuario_codigo] ? (
                        <div role="alert" className="error" style={{ color: "var(--color-brand-strong)", fontSize: "var(--text-sm)", marginTop: 4 }} data-testid={`eq-error-${r.usuario_codigo}`}>
                          {perCodeErrors[r.usuario_codigo]}
                        </div>
                      ) : null}
                    </td>
                    <td>{r.nombre ?? <span className="muted">—</span>}</td>
                    <td>
                      {r.oid ? (
                        <span className="tag tag-ok" title={r.oid}>
                          <Icon name="check" size={12} /> resuelta
                        </span>
                      ) : r.isNew ? (
                        <span className="muted small">se resuelve al guardar</span>
                      ) : (
                        <span className="tag tag-warning">sin resolver</span>
                      )}
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Activo ${r.usuario_codigo}`}
                        checked={r.activo}
                        onChange={(e) => update(i, { activo: e.target.checked })}
                      />
                    </td>
                    <td className="nowrap">{formatMexicoCity(r.actualizado_utc)}</td>
                    <td>
                      {r.isNew ? (
                        <button type="button" className="ghost small" onClick={() => removeNew(i)} aria-label="Quitar fila nueva">
                          <Icon name="x" size={16} />
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {save.error && Object.keys(perCodeErrors).length === 0 ? <ProblemAlert error={save.error} /> : null}
          {save.error && Object.keys(perCodeErrors).length > 0 ? (
            <Alert tone="error" testId="eq-problem" title="No se guardó ningún cambio">
              Uno o más correos no corresponden a una cuenta. Corrige los marcados y vuelve a guardar.
            </Alert>
          ) : null}
          {saved ? (
            <Alert tone="success" testId="eq-saved">
              Equivalencias guardadas.
            </Alert>
          ) : null}
          <div className="actions">
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setSaved(false);
                setRows([...rows, { usuario_codigo: "", correo: "", activo: true, nombre: null, oid: null, actualizado_utc: null, isNew: true }]);
              }}
            >
              <Icon name="users" size={16} /> Agregar coordinador
            </button>
            <span className="spacer" />
            {dirty && !save.isPending ? <span className="dirty-note">Cambios sin guardar</span> : null}
            <button type="submit" disabled={save.isPending} data-testid="eq-guardar" title="Guarda los cambios y vuelve a resolver las cuentas">
              {save.isPending ? "Guardando…" : "Guardar cambios"}
            </button>
          </div>
        </form>
      ) : null}
    </main>
  );
}
