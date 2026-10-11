import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

/**
 * Remove every e2e site (origen 800000-899999) through the backend CLI (audit C7). Runs inside the
 * compose network so it works however Playwright is launched (make e2e, pnpm -r test, CI).
 * Set E2E_SKIP_CLEANUP=1 to keep the data for debugging.
 */
export function e2eCleanup(): void {
  if (process.env.E2E_SKIP_CLEANUP === "1") return;
  execFileSync(
    "docker",
    [
      "compose", "run", "--rm", "--no-deps",
      "-e", "DB_HOST=sqlserver",
      "-e", "STORAGE_BLOB_ENDPOINT=http://azurite:10000/devstoreaccount1",
      "-e", "DEV_IDP_URL=http://dev-idp:8001",
      "api", "python", "-m", "app.cli", "e2e-cleanup",
    ],
    { cwd: repoRoot, stdio: ["ignore", "ignore", "inherit"] },
  );
}
