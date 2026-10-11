import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { useApi } from "../api";
import type { EquivalenciaOut } from "./types";

/** Equivalence table, shared by pages that need to show a coordinator by name instead of code or oid. */
export function useEquivalencias() {
  const api = useApi();
  return useQuery({
    queryKey: ["equivalencias"],
    queryFn: () => api.get<EquivalenciaOut[]>("/api/v1/admin/equivalencias"),
    staleTime: 5 * 60_000,
  });
}

export interface Coordinadores {
  byCode: Record<string, EquivalenciaOut>;
  byOid: Record<string, EquivalenciaOut>;
  nombre: (code: string | null | undefined) => string;
  nombrePorOid: (oid: string | null | undefined) => string | null;
}

export function useCoordinadores(): Coordinadores {
  const q = useEquivalencias();
  return useMemo(() => {
    const byCode: Record<string, EquivalenciaOut> = {};
    const byOid: Record<string, EquivalenciaOut> = {};
    for (const e of q.data ?? []) {
      byCode[e.usuario_codigo] = e;
      if (e.oid) byOid[e.oid] = e;
    }
    return {
      byCode,
      byOid,
      nombre: (code) => (code ? (byCode[code]?.nombre ?? code) : ""),
      nombrePorOid: (oid) => (oid ? (byOid[oid]?.nombre ?? null) : null),
    };
  }, [q.data]);
}
