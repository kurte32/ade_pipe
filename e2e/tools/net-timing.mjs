// Time to the coordinator site list on emulated mobile networks against a running PWA (RNF-08 evidence).
/* global process, console */
// Usage: PWA_URL=http://localhost:4173 node tools/net-timing.mjs  (from e2e/, with the stack up)
import { chromium, devices } from "@playwright/test";
const PWA = process.env.PWA_URL ?? "http://localhost:4173";
const browser = await chromium.launch();
const results = [];
for (const [label, cond] of [["slow 4G (CDP: 4 Mbps down, 3 Mbps up, 150 ms RTT)", { downloadThroughput: 4e6 / 8, uploadThroughput: 3e6 / 8, latency: 150 }], ["regular 3G (1.6 Mbps, 300 ms)", { downloadThroughput: 1.6e6 / 8, uploadThroughput: 750e3 / 8, latency: 300 }]]) {
  for (const run of ["cold", "warm (second visit, service worker)"]) {
    const context = await browser.newContext({ ...devices["Pixel 7"], storageState: run.startsWith("warm") ? results.at(-1)?.state : undefined });
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", { offline: false, ...cond });
    const t0 = Date.now();
    await page.goto(PWA + "/");
    if (!run.startsWith("warm")) {
      await page.getByTestId("dev-user-ard").click();
    }
    await page.getByTestId("sitios-list").waitFor({ state: "visible", timeout: 60000 });
    await page.locator('[data-testid^="sitio-"]').first().waitFor({ state: "visible", timeout: 60000 });
    const ms = Date.now() - t0;
    const state = await context.storageState();
    results.push({ label, run, ms, state });
    console.log(`${label} | ${run}: list visible after ${ms} ms`);
    await context.close();
  }
}
await browser.close();
