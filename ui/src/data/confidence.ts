import type { Band, BandStat, ConfidenceModel, ConfidenceModelInfo } from "@/domain/types";
import { r14Confidence } from "@/intelligence/rules";

export type ModelId = "M1" | "M2";

export interface UnitConfidence {
  model: ModelId;
  modelLabel: string;
  p: number | null;
  band: Band;
  stat: BandStat | null;
  blocked: boolean;
  reason: string;
  experimental: boolean;
}

/** Exactly the frozen model's output for a benchmark unit: no rescaling, flooring or rounding up. */
export function unitConfidence(model: ConfidenceModel | null, unitId: string, which: ModelId): UnitConfidence | null {
  if (!model) return null;
  const u = model.units[unitId];
  if (!u) return null;
  const info = model.models[which];
  return fromBand(info, u[which].band, u[which].p);
}

export function fromBand(info: ConfidenceModelInfo, band: Band, p: number | null): UnitConfidence {
  const stat = info.eval.bands.find((b) => b.band === band) ?? null;
  const r14 = r14Confidence(stat);
  return { model: info.id, modelLabel: info.label, p, band, stat, blocked: r14.verdict === "block", reason: r14.reason, experimental: info.eval.experimental };
}

/** Score a live comparator unit with a frozen model's weights (same formula as ui/scripts/calibrate.py `predict`). */
export function scoreFeatures(info: ConfidenceModelInfo, x: number[]): number {
  let z = info.intercept;
  for (let i = 0; i < info.weights.length; i++) z += ((x[i] - info.means[i]) / info.sds[i]) * info.weights[i];
  return 1 / (1 + Math.exp(-z));
}

export function bandOf(p: number | null, t: { high: number; low: number }): Band {
  if (p === null) return "Abstain";
  return p >= t.high ? "High" : p >= t.low ? "Medium" : "Low";
}
