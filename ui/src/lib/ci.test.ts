import { readJson } from "@/test/files";
import { fmtCI, ciReading, parseCI, findCIs, excludesZero } from "./ci";

const vectors = readJson<{ point: number; lo: number; hi: number; signed: boolean; reading: boolean; expected: string }[]>("src/data/ci_vectors.json");

describe("ci.ts mirrors src/eval/ci_format.py", () => {
  it("formats every Python-generated vector identically", () => {
    expect(vectors.length).toBeGreaterThan(50);
    for (const v of vectors) expect(fmtCI(v.point, v.lo, v.hi, { signed: v.signed, reading: v.reading })).toBe(v.expected);
  });
  it("reads CIs strictly against 0", () => {
    expect(ciReading(0.001, 0.2)).toBe("excludes 0 (above)");
    expect(ciReading(-0.2, -0.001)).toBe("excludes 0 (below)");
    expect(ciReading(0, 0.2)).toBe("does not exclude 0");
    expect(excludesZero(-0.028, 0)).toBe(false);
  });
  it("prints near-zero bounds to 4 decimals", () => {
    expect(fmtCI(-0.009, -0.028, 0, { signed: true, reading: true })).toBe("-0.009 [-0.028, +0.0000] (does not exclude 0)");
  });
  it("parses project CI labels", () => {
    expect(parseCI("-0.049 [-0.133, +0.036] (does not exclude 0)")).toEqual({ point: -0.049, lo: -0.133, hi: 0.036, reading: "does not exclude 0" });
    expect(parseCI("+0.451 [+0.421, +0.481] (excludes 0 (above))")?.reading).toBe("excludes 0 (above)");
    expect(findCIs("by −0.068 [−0.132, −0.012] and +0.1 [0.0, 0.2]")).toHaveLength(2);
  });
});
