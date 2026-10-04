import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";
import { join } from "node:path";

export interface Bridge { call<T = Record<string, unknown>>(req: Record<string, unknown>, timeoutMs?: number): Promise<T>; close(): void }

/** Persistent python3 server/pipeline_bridge.py, line-delimited JSON. Started lazily on the first live request. */
export class PythonBridge implements Bridge {
  private proc: ChildProcessWithoutNullStreams | null = null;
  private seq = 0;
  private pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();
  constructor(private readonly uiDir: string, private readonly python = "python3") {}

  private start() {
    if (this.proc) return this.proc;
    const p = spawn(this.python, [join(this.uiDir, "server/pipeline_bridge.py")], { cwd: this.uiDir, env: { ...process.env, HF_HUB_OFFLINE: "1" } });
    createInterface({ input: p.stdout }).on("line", (line) => {
      try {
        const msg = JSON.parse(line) as { id?: number };
        const h = msg.id !== undefined ? this.pending.get(msg.id) : undefined;
        if (h && msg.id !== undefined) { this.pending.delete(msg.id); h.resolve(msg); }
      } catch { /* ignore non-JSON lines */ }
    });
    p.stderr.on("data", () => { /* model-loading noise; never echoed (could include paths) */ });
    p.on("exit", () => { this.proc = null; for (const h of this.pending.values()) h.reject(new Error("bridge exited")); this.pending.clear(); });
    this.proc = p;
    return p;
  }

  call<T>(req: Record<string, unknown>, timeoutMs = 180_000): Promise<T> {
    const p = this.start();
    const id = ++this.seq;
    return new Promise<T>((resolve, reject) => {
      const t = setTimeout(() => { this.pending.delete(id); reject(new Error("bridge timeout")); }, timeoutMs);
      this.pending.set(id, { resolve: (v) => { clearTimeout(t); resolve(v as T); }, reject: (e) => { clearTimeout(t); reject(e); } });
      p.stdin.write(JSON.stringify({ ...req, id }) + "\n");
    });
  }

  close() { this.proc?.kill(); this.proc = null; }
}
