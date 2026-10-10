import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { useApi } from "../api";
import { getDb, getMeta, setMeta } from "../db/schema";
import type { Catalogos } from "../lib/types";

const KEY = "catalogos";
const EMPTY: Catalogos = { estatus: [], motivos_devolucion: [], tipos_documento: [] };

/** Catalogs from the API, cached in Dexie so they are available offline. */
export function useCatalogos(): Catalogos {
  const api = useApi();
  const db = getDb();
  const q = useQuery({
    queryKey: ["catalogos"],
    queryFn: async () => {
      try {
        const data = await api.get<Catalogos>("/api/v1/catalogos");
        await setMeta(db, KEY, data);
        return data;
      } catch (e) {
        const cached = await getMeta<Catalogos>(db, KEY);
        if (cached) return cached;
        throw e;
      }
    },
    staleTime: 10 * 60_000,
    retry: 0,
  });
  useEffect(() => {
    /* no-op: query handles caching */
  }, []);
  return q.data ?? EMPTY;
}

export function requiredDocTypes(c: Catalogos): Catalogos["tipos_documento"] {
  return c.tipos_documento.filter((t) => t.requerido_en_estatus === "recepcion_documentos");
}
