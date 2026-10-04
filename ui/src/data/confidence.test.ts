import { readJson } from "@/test/files";
import type { ConfidenceModel } from "@/domain/types";
import { bandOf, scoreFeatures, unitConfidence } from "./confidence";

const model = readJson<ConfidenceModel>("src/data/confidence_model_v1.json");
const frozen = readJson<{ M2: { intercept: number; weights: number[]; means: number[]; sds: number[] } }>("src/data/confidence_frozen_v1.json");

describe("confidence values in the UI equal the frozen model outputs (no post-hoc scaling)", () => {
  it("returns exactly the stored probability and band for every unit and both models", () => {
    for (const [uid, u] of Object.entries(model.units)) {
      for (const m of ["M1", "M2"] as const) {
        const c = unitConfidence(model, uid, m)!;
        expect(c.p).toBe(u[m].p);
        expect(c.band).toBe(u[m].band);
        expect(c.band).toBe(bandOf(u[m].p, model.bandThresholds));
      }
    }
  });
  it("uses the M2 parameters frozen before the gold evaluation", () => {
    const m2 = model.models.M2;
    expect(m2.weights).toEqual(frozen.M2.weights);
    expect(m2.intercept).toBe(frozen.M2.intercept);
    expect(m2.means).toEqual(frozen.M2.means);
  });
  it("shows each band's empirical accuracy, CI and n (R14), and the badge names its model", () => {
    const anyUnit = Object.keys(model.units)[0];
    const c = unitConfidence(model, anyUnit, "M2")!;
    expect(c.modelLabel).toMatch(/dev set/);
    if (c.band !== "Abstain") expect(c.stat?.wilsonCI).toBeTruthy();
    expect(unitConfidence(model, anyUnit, "M1")!.modelLabel).toBe("cross-validated on gold");
  });
  it("scoreFeatures reproduces the logistic formula", () => {
    const m2 = model.models.M2;
    const p = scoreFeatures(m2, m2.means);
    expect(p).toBeCloseTo(1 / (1 + Math.exp(-m2.intercept)), 12);
  });
});
