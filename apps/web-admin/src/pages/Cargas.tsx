import { ProblemAlert, Spinner, formatMexicoCity } from "@pipeline/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useApi } from "../api";
import type { LoteSummary } from "../lib/types";

export function Cargas() {
  const api = useApi();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);

  const lotes = useQuery({
    queryKey: ["cargas", "all"],
    queryFn: () => api.get<LoteSummary[]>("/api/v1/admin/cargas?limit=100"),
  });

  const upload = useMutation({
    mutationFn: async (f: File) => {
      const fd = new FormData();
      fd.append("file", f, f.name);
      const r = await api.post<LoteSummary>("/api/v1/admin/cargas", fd);
      return r.data;
    },
    onSuccess: async (lote) => {
      await qc.invalidateQueries({ queryKey: ["cargas"] });
      navigate(`/cargas/${lote.id}`);
    },
  });

  return (
    <main>
      <h1>Cargas</h1>
      <section className="card">
        <h2>Nueva carga</h2>
        <p className="muted">
          Archivo CSV, XLSX o XLS con las columnas #, USUARIO, REGIÓN, SITIO, COORDENADAS, GPS, POTENCIAL, CAMPOS y FECHA.
          Nada se inserta hasta confirmar la vista previa.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (file) upload.mutate(file);
          }}
        >
          <label>
            Archivo
            <input
              ref={fileRef}
              type="file"
              name="file"
              data-testid="carga-file"
              accept=".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <ProblemAlert error={upload.error} />
          <div className="actions">
            <button type="submit" disabled={!file || upload.isPending} data-testid="carga-submit">
              {upload.isPending ? "Procesando…" : "Subir y previsualizar"}
            </button>
          </div>
        </form>
      </section>

      <h2>Historial de cargas</h2>
      {lotes.isPending ? <Spinner /> : null}
      {lotes.isError ? <ProblemAlert error={lotes.error} onRetry={() => void lotes.refetch()} /> : null}
      {lotes.data ? (
        <div className="table-wrap">
          <table data-testid="cargas-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Archivo</th>
                <th>Total</th>
                <th>Ok</th>
                <th>Advertencias</th>
                <th>Errores</th>
                <th>Estado</th>
                <th>Resultado</th>
              </tr>
            </thead>
            <tbody>
              {lotes.data.map((l) => (
                <tr key={l.id}>
                  <td className="nowrap">{formatMexicoCity(l.fecha_utc)}</td>
                  <td>
                    <Link to={`/cargas/${l.id}`}>{l.archivo_nombre}</Link>
                  </td>
                  <td>{l.filas_total}</td>
                  <td>{l.filas_ok}</td>
                  <td>{l.filas_advertencia}</td>
                  <td>{l.filas_error}</td>
                  <td>{l.estado}</td>
                  <td>
                    {l.estado === "confirmado"
                      ? `${l.filas_insertadas ?? 0} insertadas, ${l.filas_actualizadas ?? 0} actualizadas, ${l.filas_revision ?? 0} en revisión`
                      : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {lotes.data.length === 0 ? <p className="muted">Sin cargas.</p> : null}
        </div>
      ) : null}
    </main>
  );
}
