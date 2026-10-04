import type { PaperClaim, Snapshot } from "@/domain/types";
import { r1ClaimCheck, r6NumberDrift } from "@/intelligence/rules";

export type ClaimStatus = "matched" | "overclaim" | "notfound" | "ambiguous" | "text";

/** ✓ matched · ⚠ CI includes 0 but the wording asserts an effect · ✗ not found · ? ambiguous (only private / unknown). */
export function claimStatus(c: PaperClaim, s: Pick<Snapshot, "results">): { status: ClaimStatus; r1: ReturnType<typeof r1ClaimCheck>; r6: ReturnType<typeof r6NumberDrift>[] } {
  const r1 = r1ClaimCheck(c, s.results);
  const r6 = c.numbers.map(r6NumberDrift);
  const status: ClaimStatus = r1.verdict === "warn" ? "overclaim" : r6.some((r) => r.verdict === "fail") ? "notfound"
    : r6.some((r) => r.verdict === "unclear") ? "ambiguous" : c.numbers.length ? "matched" : "text";
  return { status, r1, r6 };
}

export function gate(s: Snapshot) {
  const st = s.claims.map((c) => claimStatus(c, s).status);
  return {
    unmatched: st.filter((x) => x === "notfound").length,
    overclaims: st.filter((x) => x === "overclaim").length,
    ambiguous: st.filter((x) => x === "ambiguous").length,
    placeholders: s.placeholders.filter((p) => p.kind === "placeholder" || p.kind === "verify").length,
  };
}
