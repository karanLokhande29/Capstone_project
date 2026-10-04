import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export const sha256 = (s: string) => createHash("sha256").update(s).digest("hex");

/** Daily cap, persisted under server/.state (gitignored). The day rolls over in IST. */
export class Quota {
  constructor(private readonly dir: string, readonly cap: number, private readonly now: () => Date = () => new Date()) { mkdirSync(dir, { recursive: true }); }
  private day() { return new Date(this.now().getTime() + 5.5 * 3_600_000).toISOString().slice(0, 10); }
  private file() { return join(this.dir, "quota.json"); }
  used(): number {
    try {
      const j = JSON.parse(readFileSync(this.file(), "utf8")) as { day: string; used: number };
      return j.day === this.day() ? j.used : 0;
    } catch { return 0; }
  }
  remaining() { return Math.max(0, this.cap - this.used()); }
  consume() { writeFileSync(this.file(), JSON.stringify({ day: this.day(), used: this.used() + 1 })); }
}

/** Response cache keyed by the sha256 of the full prompt (cached answers do not consume quota). */
export class Cache {
  constructor(private readonly dir: string) { mkdirSync(dir, { recursive: true }); }
  get(key: string): string | null {
    const p = join(this.dir, `${key}.json`);
    return existsSync(p) ? (JSON.parse(readFileSync(p, "utf8")) as { text: string }).text : null;
  }
  set(key: string, text: string) { writeFileSync(join(this.dir, `${key}.json`), JSON.stringify({ text })); }
}

/** Reads ui/.env (KEY=VALUE lines) without logging anything; process.env wins. */
export function loadEnv(file: string): Record<string, string> {
  const out: Record<string, string> = {};
  try {
    for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
      if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, "");
    }
  } catch { /* no .env */ }
  return { ...out, ...Object.fromEntries(Object.entries(process.env).filter(([, v]) => v !== undefined)) as Record<string, string> };
}
