import { Icon, LOTE_ESTADO, PageHeader, ProblemAlert, Spinner, formatMexicoCity, usePageTitle } from "@pipeline/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useApi } from "../api";
import type { LoteSummary } from "../lib/types";

export function Cargas() {
  usePageTitle("Cargas");
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

  const pendientes = lotes.data?.filter((l) => l.estado === "vista_previa") ?? [];

  return (
    <main>
      <PageHeader title="Cargas" description="Sube el archivo de sitios, revisa la vista previa y confirma. Nada se inserta hasta confirmar." />

      <section className="card" aria-labelledby="nueva-h">
        <h2 id="nueva-h">Nueva carga</h2>
        <ol className="steps">
          <li className="current">Elige el archivo</li>
          <li>Revisa advertencias y errores</li>
          <li>Confirma</li>
        </ol>
        <p className="helper">
          CSV, XLSX o XLS con las columnas <code>#</code>, <code>USUARIO</code>, <code>REGIÓN</code>, <code>SITIO</code>, <code>COORDENADAS</code>, <code>GPS</code>,{" "}
          <code>POTENCIAL</code>, <code>CAMPOS</code> y <code>FECHA</code>. Los sitios se identifican por <code>#</code>: los nuevos se insertan y los existentes se actualizan sin tocar lo capturado.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (file) upload.mutate(file);
          }}
        >
          <label htmlFor="carga-file">Archivo</label>
          <div className="upload-zone">
            <input
              id="carga-file"
              ref={fileRef}
              type="file"
              name="file"
              data-testid="carga-file"
              accept=".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <button type="submit" disabled={!file || upload.isPending} data-testid="carga-submit">
              <Icon name="upload" size={16} />
              {upload.isPending ? "Procesando…" : "Subir y previsualizar"}
            </button>
          </div>
          <ProblemAlert error={upload.error} />
        </form>
      </section>

      <h2 style={{ marginTop: "var(--space-4)" }}>Historial de cargas</h2>
      {pendientes.length ? (
        <p className="dirty-note">
          <Icon name="alert-triangle" size={14} /> {pendientes.length} carga{pendientes.length === 1 ? "" : "s"} en vista previa sin confirmar.
        </p>
      ) : null}
      {lotes.isPending ? <Spinner /> : null}
      {lotes.isError ? <ProblemAlert error={lotes.error} onRetry={() => void lotes.refetch()} /> : null}
      {lotes.data ? (
        <div className="table-wrap">
          <table data-testid="cargas-table">
            <thead>
              <tr>
                <th scope="col">Fecha</th>
                <th scope="col">Archivo</th>
                <th scope="col">Estado</th>
                <th scope="col" className="num">
                  Filas
                </th>
                <th scope="col" className="num">
                  Correctas
                </th>
                <th scope="col" className="num">
                  Advertencias
                </th>
                <th scope="col" className="num">
                  Errores
                </th>
                <th scope="col">Resultado</th>
              </tr>
            </thead>
            <tbody>
              {lotes.data.map((l) => (
                <tr key={l.id} className={l.estado === "vista_previa" ? "is-attention" : undefined}>
                  <td className="nowrap">{formatMexicoCity(l.fecha_utc)}</td>
                  <td>
                    <Link to={`/cargas/${l.id}`}>{l.archivo_nombre}</Link>
                  </td>
                  <td>
                    <span className={`tag ${LOTE_ESTADO[l.estado]?.tone ?? ""}`}>{LOTE_ESTADO[l.estado]?.label ?? l.estado}</span>
                  </td>
                  <td className="num">{l.filas_total}</td>
                  <td className="num">{l.filas_ok}</td>
                  <td className="num">{l.filas_advertencia}</td>
                  <td className="num">{l.filas_error}</td>
                  <td>
                    {l.estado === "confirmado"
                      ? `${l.filas_insertadas ?? 0} nuevos · ${l.filas_actualizadas ?? 0} actualizados · ${l.filas_revision ?? 0} a revisión`
                      : l.estado === "vista_previa"
                        ? (
                          <Link to={`/cargas/${l.id}`}>
                            Continuar revisión{l.pendientes_decision ? ` (${l.pendientes_decision} por decidir)` : ""}
                          </Link>
                        )
                        : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {lotes.data.length === 0 ? <p className="muted" style={{ padding: "var(--space-4)" }}>Todavía no hay cargas. Sube el primer archivo arriba.</p> : null}
        </div>
      ) : null}
    </main>
  );
}
