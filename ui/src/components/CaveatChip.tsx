import { useData } from "@/data/store";
import { useDrawer } from "./drawerState";
import { Tip } from "./ui/primitives";
import { cn } from "@/lib/utils";

const TONE: Record<string, string> = {
  by_construction: "bg-warn-soft text-warn", circular: "bg-neg-soft text-neg", single_expert: "bg-warn-soft text-warn",
  small_n: "bg-panel-2 text-ink-2", bias: "bg-warn-soft text-warn", superseded: "bg-panel-2 text-ink-3", exploratory: "bg-panel-2 text-ink-2",
  in_sample: "bg-panel-2 text-ink-2", scoring: "bg-warn-soft text-warn", item_set: "bg-panel-2 text-ink-2", scope: "bg-panel-2 text-ink-2",
  missing_ci: "bg-panel-2 text-ink-2",
};

const SHORT: Record<string, string> = {
  single_expert: "single-expert gold", scoring_asymmetry: "abstentions = errors", by_construction: "by construction", circular: "circular",
  candidates_shown: "candidates shown", item_set_102: "102 items", small_n_t4: "small T4", repair_exploratory: "exploratory repair",
  dev_used_for_development: "dev used once", flash_lite: "Flash-Lite only", per_class_small_n: "small per-class n", retest_short_gap: "short retest gap",
  no_ci_different_f1: "no CI", amended_text_only: "amended text only", calibration: "wide CIs", in_sample_majority: "in-sample",
  superseded_150k: "superseded", t3_parser_defect: "parser defect", bias_t2_xclass_t1: "favours dense", bias_t2_xclass_p2002: "favours dense",
  bias_t2_supp_p2003: "favours BM25",
};

export function CaveatChip({ id, className }: { id: string; className?: string }) {
  const c = useData((s) => s.snapshot?.caveats.find((x) => x.id === id));
  const open = useDrawer((s) => s.open);
  if (!c) return null;
  return (
    <Tip content={<span className="block max-w-xs">{c.text}<span className="mt-1 block text-ink-3">caveat:{c.id} · {c.kind}</span></span>}>
      <button type="button" onClick={() => open(`caveat:${c.id}`)}
        className={cn("cursor-pointer rounded px-1.5 py-0.5 text-[10.5px] font-medium leading-none", TONE[c.kind] ?? "bg-panel-2", className)}>
        {SHORT[c.id] ?? c.kind.replace("_", " ")}
      </button>
    </Tip>
  );
}

export function CaveatChips({ ids, className }: { ids: string[]; className?: string }) {
  return <span className={cn("inline-flex flex-wrap gap-1", className)}>{[...new Set(ids)].map((id) => <CaveatChip key={id} id={id} />)}</span>;
}
