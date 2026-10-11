import { e2eCleanup } from "./helpers/cleanup";

export default async function globalTeardown(): Promise<void> {
  e2eCleanup();
}
