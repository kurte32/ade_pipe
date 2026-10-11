import { ApiError } from "@pipeline/api-client";
import { ProblemAlert, Spinner, formatMexicoCity } from "@pipeline/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

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

export function Equivalencias() {
  const api = useApi();
  const qc = useQueryClient();
  const [rows, setRows] = useState<Row[]>([]);
  const [saved, setSaved] = useState(false);

  const q = useQuery({
    queryKey: ["equivalencias"],
    queryFn: () => api.get<EquivalenciaOut[]>("/api/v1/admin/equivalencias"),
  });
  useEffect(() => {
    if (q.data) setRows(q.data.map((e) => ({ ...e, actualizado_utc: e.actualizado_utc })));
  }, [q.data]);

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

  return (
    <main>
      <h1>Equivalencias usuario → correo</h1>
      <p className="muted">
        Cada código USUARIO del archivo de carga se resuelve a una cuenta corporativa. El cambio queda auditado. Si un correo no
        resuelve a una cuenta, no se guarda ninguna fila.
      </p>
      {q.isPending ? <Spinner /> : null}
      {q.isError ? <ProblemAlert error={q.error} onRetry={() => void q.refetch()} /> : null}
      {q.data ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="table-wrap">
            <table data-testid="equivalencias-table">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Correo</th>
                  <th>Nombre</th>
                  <th>oid</th>
                  <th>Activo</th>
                  <th>Actualizado</th>
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
                        value={r.correo}
                        onChange={(e) => update(i, { correo: e.target.value })}
                      />
                      {perCodeErrors[r.usuario_codigo] ? (
                        <div role="alert" className="pending" data-testid={`eq-error-${r.usuario_codigo}`}>
                          {perCodeErrors[r.usuario_codigo]}
                        </div>
                      ) : null}
                    </td>
                    <td>{r.nombre ?? <span className="muted">—</span>}</td>
                    <td className="muted">{r.oid ?? "sin resolver"}</td>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Activo ${r.usuario_codigo}`}
                        style={{ width: "auto", minHeight: 0 }}
                        checked={r.activo}
                        onChange={(e) => update(i, { activo: e.target.checked })}
                      />
                    </td>
                    <td className="nowrap">{formatMexicoCity(r.actualizado_utc)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {save.error && Object.keys(perCodeErrors).length === 0 ? <ProblemAlert error={save.error} /> : null}
          {save.error && Object.keys(perCodeErrors).length > 0 ? (
            <p role="alert" className="problem" data-testid="eq-problem">
              Una o más equivalencias no resuelven a una cuenta. Corrige los correos marcados.
            </p>
          ) : null}
          {saved ? (
            <div className="success" role="status" data-testid="eq-saved">
              Equivalencias guardadas.
            </div>
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
              Agregar fila
            </button>
            <button type="submit" disabled={save.isPending} data-testid="eq-guardar">
              Guardar
            </button>
          </div>
        </form>
      ) : null}
    </main>
  );
}
