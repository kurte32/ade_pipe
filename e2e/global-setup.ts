import { ADMIN_CLIENT_ID, API_URL, api, mintToken } from "./helpers/auth";
import { POOL_ARD, POOL_FIRST, POOL_USA } from "./helpers/pool";

/** Load a fresh pool of prospectado sites through the real bulk-load path before the suite. */
export default async function globalSetup(): Promise<void> {
  const header = "#,USUARIO,REGION,SITIO,COORDENADAS,GPS,POTENCIAL,CAMPOS,FECHA";
  const rows: string[] = [];
  for (let i = 0; i < POOL_ARD + POOL_USA; i++) {
    const id = POOL_FIRST + i;
    const user = i < POOL_ARD ? "ard" : "usa";
    const region = i < POOL_ARD ? "Xalapa" : "Azcapotzalco";
    const lat = (19.3 + i * 0.02).toFixed(5);
    const lon = (-96.7 - i * 0.02).toFixed(5);
    rows.push(`${id},${user},${region},Sitio Pool ${id},"${lat}, ${lon}",5.0,Alto,24/24,10/01/2026 09:00:00`);
  }
  const csv = [header, ...rows].join("\n") + "\n";
  const token = await mintToken("adm", ADMIN_CLIENT_ID);

  const form = new FormData();
  form.append("file", new Blob([csv], { type: "text/csv" }), "e2e-pool.csv");
  const up = await fetch(`${API_URL}/api/v1/admin/cargas`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}` },
    body: form,
  });
  const lote = (await up.json()) as { id: string; filas_error: number };
  if (up.status !== 201) throw new Error(`pool upload failed ${up.status} ${JSON.stringify(lote)}`);
  if (lote.filas_error) throw new Error(`pool rows with errors: ${lote.filas_error}`);

  const detail = await api<{ filas: { items: { num_fila: number; resultado: string }[] } }>(
    "GET",
    `/api/v1/admin/cargas/${lote.id}?limit=500&resultado=advertencia`,
    token,
  );
  const decisions = detail.data.filas.items.map((f) => ({ num_fila: f.num_fila, decision: "aprobar" }));
  if (decisions.length) {
    const d = await api("POST", `/api/v1/admin/cargas/${lote.id}/decisiones`, token, decisions);
    if (d.status !== 200) throw new Error(`pool decisions failed ${d.status}`);
  }
  const done = await api("POST", `/api/v1/admin/cargas/${lote.id}/confirmar`, token);
  if (done.status !== 200) throw new Error(`pool confirm failed ${done.status} ${JSON.stringify(done.data)}`);
}
