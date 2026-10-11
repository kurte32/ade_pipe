import { useQuery } from "@tanstack/react-query";

import { useApi } from "../api";
import { getDb, getMeta, setMeta } from "../db/schema";
import type { NotificacionList } from "./types";

const KEY = "notificaciones";

/** Notifications from the API, cached in Dexie so the list (and the unread count) survive offline. */
export function useNotificaciones() {
  const api = useApi();
  return useQuery({
    queryKey: ["notificaciones"],
    queryFn: async () => {
      try {
        const data = await api.get<NotificacionList>("/api/v1/notificaciones");
        await setMeta(getDb(), KEY, data);
        return data;
      } catch (e) {
        const cached = await getMeta<NotificacionList>(getDb(), KEY);
        if (cached) return cached;
        throw e;
      }
    },
    retry: 0,
    staleTime: 60_000,
  });
}
