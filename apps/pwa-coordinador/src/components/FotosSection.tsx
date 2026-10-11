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
  const [failed, setFailed] = useState(false);
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
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [api, archivoId]);
  if (failed) return <span className="muted">(sin conexión)</span>;
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

  return (
    <section aria-labelledby="fotos-h">
      <h2 id="fotos-h">Fotos del inmueble</h2>
      <p className="muted">Opcionales. Se comprimen en el teléfono y se envían al sincronizar.</p>
      <label htmlFor="foto-input" className="button" style={{ display: "inline-block" }}>
        {busy ? "Procesando…" : "Tomar o elegir foto"}
      </label>
      <input
        id="foto-input"
        type="file"
        accept="image/*"
        capture="environment"
        onChange={(e) => void onFile(e)}
        disabled={busy || disabled}
        style={{ position: "absolute", width: 1, height: 1, opacity: 0 }}
        data-testid="foto-input"
      />
      {error ? <p role="alert" className="problem">{error}</p> : null}
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
            <figcaption className="muted">{a.nombre_original}</figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}
