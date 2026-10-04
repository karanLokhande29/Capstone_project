// Mirrors src/eval/ci_format.py exactly: 3 decimals; a bound with |x| < 0.0005 prints to 4 decimals; a CI excludes 0 only
// when strictly above or below.

export const ABOVE = "excludes 0 (above)";
export const BELOW = "excludes 0 (below)";
export const NEITHER = "does not exclude 0";
export type CIReading = typeof ABOVE | typeof BELOW | typeof NEITHER;

export function ciReading(lo: number, hi: number): CIReading {
  if (lo > 0) return ABOVE;
  if (hi < 0) return BELOW;
  return NEITHER;
}

export function excludesZero(lo: number, hi: number): boolean {
  return ciReading(lo, hi) !== NEITHER;
}

function fixed(x: number, d: number, signed: boolean): string {
  const neg = x < 0 || Object.is(x, -0);
  const body = Math.abs(x).toFixed(d);
  if (signed) return (neg ? "-" : "+") + body;
  return (neg ? "-" : "") + body;
}

export function fmtBound(x: number, signed: boolean): string {
  return fixed(x, Math.abs(x) < 0.0005 ? 4 : 3, signed);
}

export function fmtCI(point: number, lo: number, hi: number, opts: { signed?: boolean; reading?: boolean } = {}): string {
  const signed = !!opts.signed;
  const p = fixed(point, 3, signed);
  const out = `${p} [${fmtBound(lo, signed)}, ${fmtBound(hi, signed)}]`;
  return opts.reading ? `${out} (${ciReading(lo, hi)})` : out;
}

/** Parse a project-labelled CI string such as "-0.049 [-0.133, +0.036] (does not exclude 0)". */
export function parseCI(s: string): { point: number; lo: number; hi: number; reading: CIReading | null } | null {
  const m = s.replace(/−/g, "-").match(/([+-]?\d+(?:\.\d+)?)\s*\[\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\](?:\s*\(([^)]*\)?)\))?/);
  if (!m) return null;
  const reading = m[4] ? (m[4].trim() as CIReading) : null;
  return { point: Number(m[1]), lo: Number(m[2]), hi: Number(m[3]), reading };
}

/** Every "x [lo, hi]" occurrence in a sentence. */
export function findCIs(s: string): { point: number; lo: number; hi: number; text: string }[] {
  const re = /([+-]?\d+(?:\.\d+)?)\s*\[\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\]/g;
  const out: { point: number; lo: number; hi: number; text: string }[] = [];
  for (const m of s.replace(/−/g, "-").matchAll(re)) out.push({ point: Number(m[1]), lo: Number(m[2]), hi: Number(m[3]), text: m[0] });
  return out;
}
