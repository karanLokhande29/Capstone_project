import { useJson } from "../data";
import { Loading } from "../DemoLayout";
import type { CostShard } from "../types";

/** Tokens from the LLM call ledger. No price is recorded in the repository, so none is invented. */
export function CostMeter({ live }: { live?: { inputTokens: number | null; outputTokens: number | null; latencyMs: number } | null }) {
  const c = useJson<CostShard>("cost.json").data;
  if (!c) return <Loading what="the call ledger" />;
  const f = (x: number) => Math.round(x).toLocaleString("en-IN");
  return (
    <div className="space-y-2 text-[13.5px]">
      {/* Label above value: the side column is too narrow for both on one line. */}
      <dl className="grid gap-y-0.5 [&_dd]:mb-1.5 [&_dd]:text-ink">
        <dt className="text-ink-2">Per comparator call (mean of {c.t1.calls})</dt><dd className="num">{f(c.t1.perCall.input)} in · {f(c.t1.perCall.output)} out tokens</dd>
        <dt className="text-ink-2">Full 412-pair benchmark run</dt><dd className="num">{f(c.t1.inputTokens)} in · {f(c.t1.outputTokens)} out tokens</dd>
        <dt className="text-ink-2">Development runs (2 × 92 calls)</dt><dd className="num">{f(c.dev.inputTokens)} in · {f(c.dev.outputTokens)} out tokens</dd>
        {live && <><dt className="text-ink-2">This live call</dt><dd className="num">{live.inputTokens != null ? `${f(live.inputTokens)} in · ${f(live.outputTokens ?? 0)} out` : "tokens not reported"} · {(live.latencyMs / 1000).toFixed(1)} s</dd></>}
      </dl>
      <p className="text-[12px] text-ink-3">{c.priceNote} Source: the project's LLM call ledger (logs/llm_calls.jsonl).</p>
    </div>
  );
}
