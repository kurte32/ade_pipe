/**
 * Site pool provisioned for each e2e run (audit C7). Specs pick only from this id range, so the
 * seeded data is never consumed; `make e2e` removes everything in 800000-899999 before and after.
 */
export const POOL_FIRST = 890_000;
export const POOL_ARD = 10;
export const POOL_USA = 2;
export const POOL_LAST = POOL_FIRST + POOL_ARD + POOL_USA - 1;

export function inPool(origenId: number): boolean {
  return origenId >= POOL_FIRST && origenId <= POOL_LAST;
}
