import { useAuth } from "@pipeline/auth/react";
import { useLiveQuery } from "dexie-react-hooks";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { useApi } from "../api";
import { getDb, getMeta, type OperacionTipo } from "../db/schema";
import { META_LAST_SYNC, enqueue, syncAll, type SyncDeps, type SyncOutcome } from "./engine";

export interface SyncState {
  online: boolean;
  syncing: boolean;
  needsLogin: boolean;
  lastSyncAt: number | null;
  lastOutcome: SyncOutcome | null;
  lastError: string | null;
  pendingCount: number;
  blockedCount: number;
  syncNow: () => Promise<SyncOutcome | null>;
  enqueueOp: (sitioId: number, tipo: OperacionTipo, payload: unknown) => Promise<void>;
  deps: SyncDeps;
}

const SyncContext = createContext<SyncState | null>(null);
const INTERVAL_MS = 30_000;

export function SyncProvider({ children }: { children: ReactNode }) {
  const api = useApi();
  const { account } = useAuth();
  const db = useMemo(() => getDb(), []);
  const deps = useMemo<SyncDeps>(() => ({ api, db }), [api, db]);
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  const [syncing, setSyncing] = useState(false);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [lastOutcome, setLastOutcome] = useState<SyncOutcome | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null);
  const inFlight = useRef<Promise<SyncOutcome | null> | null>(null);
  const rerun = useRef(false);

  const pendingCount = useLiveQuery(
    () => db.operaciones.where("estado").anyOf(["pendiente", "enviando", "error"]).count(),
    [db],
    0,
  );
  const blockedCount = useLiveQuery(() => db.operaciones.where("estado").equals("bloqueada").count(), [db], 0);

  useEffect(() => {
    getMeta<number>(db, META_LAST_SYNC).then((v) => setLastSyncAt(v ?? null));
  }, [db]);

  const syncNow = useCallback(async (): Promise<SyncOutcome | null> => {
    if (!account) return null;
    if (inFlight.current) {
      // Something was enqueued while a sync is running: run once more when it finishes.
      rerun.current = true;
      return inFlight.current;
    }
    setSyncing(true);
    const run = async (): Promise<SyncOutcome | null> => {
      let last: SyncOutcome | null = null;
      do {
        rerun.current = false;
        try {
          const outcome = await syncAll(deps);
          last = outcome;
          setLastOutcome(outcome);
          setNeedsLogin(outcome.needsLogin);
          setLastError(null);
          if (!outcome.offline && !outcome.needsLogin) setLastSyncAt(Date.now());
          if (outcome.offline || outcome.needsLogin) rerun.current = false;
        } catch (e) {
          setLastError(e instanceof Error ? e.message : String(e));
          rerun.current = false;
        }
      } while (rerun.current);
      return last;
    };
    const p = run().finally(() => {
      setSyncing(false);
      inFlight.current = null;
    });
    inFlight.current = p;
    return p;
  }, [account, deps]);

  const enqueueOp = useCallback(
    async (sitioId: number, tipo: OperacionTipo, payload: unknown) => {
      await enqueue(deps, sitioId, tipo, payload);
      if (navigator.onLine) void syncNow();
    },
    [deps, syncNow],
  );

  useEffect(() => {
    const on = () => {
      setOnline(true);
      void syncNow();
    };
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    const timer = window.setInterval(() => {
      if (navigator.onLine) void syncNow();
    }, INTERVAL_MS);
    if (navigator.onLine) void syncNow();
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
      window.clearInterval(timer);
    };
  }, [syncNow]);

  const value = useMemo<SyncState>(
    () => ({
      online,
      syncing,
      needsLogin,
      lastSyncAt,
      lastOutcome,
      lastError,
      pendingCount: pendingCount ?? 0,
      blockedCount: blockedCount ?? 0,
      syncNow,
      enqueueOp,
      deps,
    }),
    [online, syncing, needsLogin, lastSyncAt, lastOutcome, lastError, pendingCount, blockedCount, syncNow, enqueueOp, deps],
  );
  return <SyncContext.Provider value={value}>{children}</SyncContext.Provider>;
}

export function useSync(): SyncState {
  const ctx = useContext(SyncContext);
  if (!ctx) throw new Error("useSync debe usarse dentro de SyncProvider");
  return ctx;
}
