import { ApiError } from "@pipeline/api-client";
import { Alert, Icon, formatMexicoCity } from "@pipeline/ui";
import { useState } from "react";

import { useApi } from "../api";
import { getDb } from "../db/schema";
import type { ArchivoOut, Catalogos } from "../lib/types";
import { useSync } from "../sync/context";
import { uploadDocument, type UploadProgress } from "../upload/resumable";

function describe(p: UploadProgress | null): string {
  if (!p) return "";
  if (p.phase === "hash") return "Calculando huella del archivo…";
  if (p.phase === "upload") return `Subiendo ${Math.round((p.sent / Math.max(1, p.total)) * 100)} %`;
  if (p.phase === "verify") return "Validando en el servidor…";
  return "Listo";
}

export function DocumentosSection({
  sitioId,
  tipos,
  archivos,
  onPublished,
  disabled,
}: {
  sitioId: number;
  tipos: Catalogos["tipos_documento"];
  archivos: ArchivoOut[];
  onPublished: () => Promise<void>;
  disabled?: boolean;
}) {
  const api = useApi();
  const sync = useSync();
  const [progress, setProgress] = useState<Record<string, UploadProgress | null>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [info, setInfo] = useState<Record<string, string>>({});

  async function onFile(tipoId: string, e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setErrors((x) => ({ ...x, [tipoId]: "Solo se aceptan archivos PDF." }));
      return;
    }
    setErrors((x) => ({ ...x, [tipoId]: "" }));
    setInfo((x) => ({ ...x, [tipoId]: "" }));
    try {
      const result = await uploadDocument({
        api,
        db: getDb(),
        sitioId,
        tipoDocumento: tipoId,
        file,
        onProgress: (p) => setProgress((x) => ({ ...x, [tipoId]: p })),
      });
      if (result.estado === "escaneando") {
        setInfo((x) => ({ ...x, [tipoId]: "Recibido. Se publicará cuando termine la revisión antimalware." }));
      }
      await onPublished();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : err instanceof Error ? err.message : String(err);
      setErrors((x) => ({ ...x, [tipoId]: msg }));
    } finally {
      setProgress((x) => ({ ...x, [tipoId]: null }));
    }
  }

  async function descargar(a: ArchivoOut) {
    try {
      const r = await api.fetchRaw(`/api/v1/archivos/${a.id}`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = a.nombre_original;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (err) {
      setErrors((x) => ({ ...x, [a.tipo_documento ?? a.id]: err instanceof Error ? err.message : String(err) }));
    }
  }

  const cargados = tipos.filter((t) => archivos.some((a) => a.tipo === "documento" && a.tipo_documento === t.id && a.vigente && a.estado === "publicado")).length;

  return (
    <section aria-labelledby="docs-h">
      <div className="card-head">
        <h2 id="docs-h">Documentos</h2>
        <span className={`tag ${cargados === tipos.length && tipos.length ? "tag-ok" : "tag-muted"}`}>
          {cargados} de {tipos.length}
        </span>
      </div>
      <p className="section-sub">PDF, hasta la última versión de cada uno. Se necesitan los {tipos.length} para Recepción de documentos.</p>
      {!sync.online ? (
        <Alert tone="neutral" icon="wifi-off">
          Los PDF se suben con señal. Podrás subirlos al recuperar conexión.
        </Alert>
      ) : null}
      <ul className="docs">
        {tipos.map((t) => {
          const vigente = archivos.find((a) => a.tipo === "documento" && a.tipo_documento === t.id && a.vigente && a.estado === "publicado");
          const p = progress[t.id] ?? null;
          return (
            <li key={t.id} data-testid={`doc-${t.id}`}>
              <Icon name="file-text" className={vigente ? "" : "muted"} />
              <div className="doc-body">
                <span className="doc-name">
                  {t.nombre}
                  {vigente ? <span className="tag tag-ok">cargado · v{vigente.version}</span> : <span className="tag tag-muted">falta</span>}
                </span>
                {vigente ? (
                  <span className="doc-meta">
                    {vigente.nombre_original} · {vigente.paginas ?? "?"} páginas · {formatMexicoCity(vigente.subido_utc)}
                  </span>
                ) : null}
                {p ? (
                  <span className="pending" role="status">
                    <Icon name="upload" size={14} /> {describe(p)}
                  </span>
                ) : null}
                {errors[t.id] ? (
                  <p role="alert" className="error" style={{ color: "var(--color-brand-strong)", fontSize: "var(--text-sm)", margin: "4px 0 0" }}>
                    {errors[t.id]}
                  </p>
                ) : null}
                {info[t.id] ? <p className="pending">{info[t.id]}</p> : null}
              </div>
              <div className="doc-actions">
                {vigente ? (
                  <button type="button" className="ghost small" onClick={() => void descargar(vigente)} data-testid={`descargar-${t.id}`}>
                    <Icon name="download" size={16} /> Descargar
                  </button>
                ) : null}
                <span className="file-button">
                  <span className="button small secondary" aria-hidden="true">
                    <Icon name="upload" size={16} /> {vigente ? "Reemplazar" : "Subir PDF"}
                  </span>
                  <input
                    id={`doc-input-${t.id}`}
                    type="file"
                    accept="application/pdf"
                    aria-label={`${vigente ? "Reemplazar" : "Subir"} PDF: ${t.nombre}`}
                    onChange={(e) => void onFile(t.id, e)}
                    disabled={!sync.online || !!p || disabled}
                    data-testid={`doc-input-${t.id}`}
                  />
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
