import { ApiError } from "@pipeline/api-client";
import { Icon } from "@pipeline/ui";
import { useEffect, useState } from "react";

import { useApi } from "../api";
import { getDb } from "../db/schema";
import { compressPhoto } from "../lib/photos";
import type { ArchivoOut } from "../lib/types";
import { useFotosLocales } from "../lib/useSitios";
import { useSync } from "../sync/context";
import { sha256Hex } from "../upload/sha256";

function LocalThumb({ blob, alt }: { blob: Blob; alt: string }) {
  const [url, setUrl] = useState<string>("");
  useEffect(() => {
    const u = URL.createObjectURL(blob);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [blob]);
  return url ? <img src={url} alt={alt} className="thumb" /> : null;
}

function RemoteThumb({ archivoId, alt }: { archivoId: string; alt: string }) {
  const api = useApi();
  const [url, setUrl] = useState<string>("");
  const [failed, setFailed] = useState<false | "offline" | "gone">(false);
  useEffect(() => {
    let objectUrl = "";
    let cancelled = false;
    api
      .fetchRaw(`/api/v1/archivos/${archivoId}`)
      .then((r) => r.blob())
      .then((b) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(b);
        setUrl(objectUrl);
      })
      .catch((e: unknown) => setFailed(e instanceof ApiError && (e.status === 404 || e.status === 410) ? "gone" : "offline"));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [api, archivoId]);
  if (failed === "gone") return <span className="muted small">(ya no disponible)</span>;
  if (failed) return <span className="muted small">(sin conexión)</span>;
  return url ? <img src={url} alt={alt} className="thumb" data-testid={`foto-${archivoId}`} /> : <span className="muted">…</span>;
}

export function FotosSection({ sitioId, publicadas, disabled }: { sitioId: number; publicadas: ArchivoOut[]; disabled?: boolean }) {
  const locales = useFotosLocales(sitioId);
  const sync = useSync();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const blob = await compressPhoto(file);
      const sha = await sha256Hex(blob);
      const id = crypto.randomUUID();
      const nombre = file.name.replace(/\.[^.]+$/, "") + ".jpg";
      await getDb().fotos.add({ id, sitioId, blob, nombre, sha256: sha, bytes: blob.size, createdAt: Date.now() });
      await sync.enqueueOp(sitioId, "foto", { fotoId: id });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const total = (locales?.length ?? 0) + publicadas.length;

  return (
    <section aria-labelledby="fotos-h">
      <div className="card-head">
        <h2 id="fotos-h">Fotos del inmueble</h2>
        {total ? <span className="tag tag-muted">{total}</span> : null}
      </div>
      <p className="section-sub">Opcionales. Se comprimen en el teléfono y se envían al sincronizar, también sin señal.</p>
      <span className="file-button">
        <span className="button secondary" aria-hidden="true">
          <Icon name="camera" size={18} /> {busy ? "Procesando…" : "Tomar o elegir foto"}
        </span>
        <input
          id="foto-input"
          type="file"
          accept="image/*"
          capture="environment"
          aria-label="Tomar o elegir foto"
          onChange={(e) => void onFile(e)}
          disabled={busy || disabled}
          data-testid="foto-input"
        />
      </span>
      {error ? (
        <p role="alert" className="problem">
          {error}
        </p>
      ) : null}
      {total ? (
        <div className="thumbs">
          {(locales ?? []).map((f) => (
            <figure key={f.id} data-testid="foto-local">
              <LocalThumb blob={f.blob} alt={f.nombre} />
              <figcaption className="pending">pendiente de sincronizar</figcaption>
            </figure>
          ))}
          {publicadas.map((a) => (
            <figure key={a.id}>
              <RemoteThumb archivoId={a.id} alt={a.nombre_original} />
              <figcaption>{a.nombre_original}</figcaption>
            </figure>
          ))}
        </div>
      ) : null}
    </section>
  );
}
