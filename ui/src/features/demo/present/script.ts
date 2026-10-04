/** The default ~3-minute presenter script (Demo Build Spec, Phase I). */
export type StepId = "guess" | "reveal" | "microscope" | "live" | "edit" | "triage" | "failures" | "close";

export const STEPS: { id: StepId; title: string; headline: string }[] = [
  { id: "guess", title: "Guess", headline: "These two rules look the same. Same requirement, different, or no matching rule?" },
  { id: "reveal", title: "Reveal", headline: "The expert says different. All five AI systems missed it; the structured comparator caught it." },
  { id: "microscope", title: "Microscope", headline: "The model only extracts 13 fields. A fixed rule, frozen before any test, decides." },
  { id: "live", title: "Live re-run", headline: "The same frozen prompt and rule, run again, next to the sealed output." },
  { id: "edit", title: "Edit", headline: "Change one value in the target rule and run it again." },
  { id: "triage", title: "Triage", headline: "How much could a team let the system handle?" },
  { id: "failures", title: "Failure Map", headline: "It wasn't one case: 56 real differences no LLM system caught." },
  { id: "close", title: "Close", headline: "And the popular metric would have rewarded copying." },
];

/** Steps that need the backend; hidden when neither a live model nor a recorded replay is available. */
export const LIVE_STEP_IDS: StepId[] = ["live", "edit"];
