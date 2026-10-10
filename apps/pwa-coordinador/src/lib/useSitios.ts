import { useLiveQuery } from "dexie-react-hooks";

import { getDb, type CachedSitio, type Operacion } from "../db/schema";

export function useCachedSitios(): CachedSitio[] | undefined {
  const db = getDb();
  return useLiveQuery(() => db.sitios.orderBy("id").toArray(), [db]);
}

export function useCachedSitio(id: number): CachedSitio | null | undefined {
  const db = getDb();
  return useLiveQuery(async () => (await db.sitios.get(id)) ?? null, [db, id]);
}

export function useOperaciones(sitioId?: number): Operacion[] | undefined {
  const db = getDb();
  return useLiveQuery(
    () => (sitioId === undefined ? db.operaciones.orderBy("seq").toArray() : db.operaciones.where("sitioId").equals(sitioId).sortBy("seq")),
    [db, sitioId],
  );
}

export function useFotosLocales(sitioId: number) {
  const db = getDb();
  return useLiveQuery(() => db.fotos.where("sitioId").equals(sitioId).toArray(), [db, sitioId]);
}
