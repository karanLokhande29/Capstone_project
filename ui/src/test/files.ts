import { readFileSync } from "node:fs";
import { join } from "node:path";

/** Read a JSON file relative to ui/ (vitest runs with cwd = ui/). */
export function readJson<T>(rel: string): T {
  return JSON.parse(readFileSync(join(process.cwd(), rel), "utf8")) as T;
}
