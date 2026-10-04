// Resolve a dotted key path into reports/results_v2.json (lists by index), e.g. "phase4.t1_paired.<label>.flag_macro_f1".
// Labels may contain spaces, "−" and ":" but never ".", so splitting on "." is safe (ingest asserts the same).

export function resolveKey(root: unknown, key: string): unknown {
  let v: unknown = root;
  for (const part of key.split(".")) {
    if (v === null || v === undefined) return undefined;
    if (Array.isArray(v)) v = v[Number(part)];
    else if (typeof v === "object") v = (v as Record<string, unknown>)[part];
    else return undefined;
  }
  return v;
}

export function resolveNumber(root: unknown, key: string): number {
  const v = resolveKey(root, key);
  if (typeof v !== "number") throw new Error(`results key is not a number: ${key}`);
  return v;
}

export const RESULTS_FILE = "reports/results_v2.json";
