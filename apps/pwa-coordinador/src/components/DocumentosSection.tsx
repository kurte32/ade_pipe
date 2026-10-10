import { ApiError } from "@pipeline/api-client";
import { formatMexicoCity } from "@pipeline/ui";
import { useRef, useState } from "react";

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
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});

  async function onFile(tipoId: string, e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setErrors((x) => ({ ...x, [tipoId]: "Solo se aceptan archivos PDF" }));
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

  return (
    <section aria-labelledby="docs-h">
      <h2 id="docs-h">Documentos requeridos</h2>
      {!sync.online ? <p className="pending">Los PDF requieren conexión. Podrás subirlos al recuperar señal.</p> : null}
      <ul className="list">
        {tipos.map((t) => {
          const vigente = archivos.find((a) => a.tipo === "documento" && a.tipo_documento === t.id && a.vigente && a.estado === "publicado");
          const p = progress[t.id] ?? null;
          return (
            <li key={t.id} data-testid={`doc-${t.id}`} style={{ padding: 12 }}>
              <strong>{t.nombre}</strong>{" "}
              {vigente ? (
                <span className="badge badge-recepcion_documentos">cargado · v{vigente.version}</span>
              ) : (
                <span className="badge badge-devuelto">falta</span>
              )}
              {vigente ? (
                <div className="muted">
                  {vigente.nombre_original} · {vigente.paginas ?? "?"} páginas · {formatMexicoCity(vigente.subido_utc)}{" "}
                  <button type="button" className="secondary" onClick={() => void descargar(vigente)} data-testid={`descargar-${t.id}`}>
                    Descargar
                  </button>
                </div>
              ) : null}
              <div className="row" style={{ marginTop: 8 }}>
                <label htmlFor={`doc-input-${t.id}`} className="button" style={{ display: "inline-block" }}>
                  {vigente ? "Reemplazar PDF" : "Subir PDF"}
                </label>
                <input
                  id={`doc-input-${t.id}`}
                  type="file"
                  accept="application/pdf"
                  ref={(el) => {
                    inputs.current[t.id] = el;
                  }}
                  onChange={(e) => void onFile(t.id, e)}
                  disabled={!sync.online || !!p || disabled}
                  style={{ position: "absolute", width: 1, height: 1, opacity: 0 }}
                  data-testid={`doc-input-${t.id}`}
                />
                {p ? (
                  <span className="pending" role="status">
                    {describe(p)}
                  </span>
                ) : null}
              </div>
              {errors[t.id] ? (
                <p role="alert" className="problem">
                  {errors[t.id]}
                </p>
              ) : null}
              {info[t.id] ? <p className="pending">{info[t.id]}</p> : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
